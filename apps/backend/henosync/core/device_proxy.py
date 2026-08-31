import logging
import math
from typing import Any, Optional

from ..models import (
    BatteryData,
    CameraFeed,
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    CommandType,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    GPSData,
    LidarScan,
    Node,
    NodeStatus,
    Position,
)
from ..plugin_system.registry import plugin_registry

logger = logging.getLogger(__name__)

# Earth radius in metres
EARTH_RADIUS = 6371000.0


class DeviceProxy:
    """
    Universal interface to any connected device.

    Control plugins ONLY interact with devices through this class.
    Never directly through device plugins.

    Handles:
    - Universal WGS84 coordinate system for all movement
    - Coordinate conversion for GPS-less devices
    - Capability data retrieval from typed TelemetryFrame fields
    - Command dispatch via CommandEnvelope through the device plugin
    - Availability and status tracking
    """

    def __init__(self, node: Node):
        self._node = node

    # ── Identity ──────────────────────────────────────────────

    @property
    def id(self) -> str:
        return self._node.id

    @property
    def name(self) -> str:
        return self._node.name

    @property
    def category(self) -> DeviceCategory:
        if self._node.specs:
            return self._node.specs.category
        return DeviceCategory.UNKNOWN

    @property
    def specs(self) -> Optional[DeviceSpecs]:
        return self._node.specs

    @property
    def local_origin(self):
        return self._node.local_origin

    @property
    def is_online(self) -> bool:
        return self._node.status == NodeStatus.ONLINE

    @property
    def is_available(self) -> bool:
        return self.is_online

    @property
    def position(self) -> Position:
        return self._node.position

    @property
    def battery_percent(self) -> Optional[float]:
        return self._node.battery_percent

    # ── Capability Checks ──────────────────────────────────────

    def has_capability(self, capability: DeviceCapability) -> bool:
        if not self._node.specs:
            return False
        return any(c.capability == capability for c in self._node.specs.capabilities)

    def get_capability_spec(
        self, capability: DeviceCapability
    ) -> Optional[CapabilitySpec]:
        if not self._node.specs:
            return None
        for cap in self._node.specs.capabilities:
            if cap.capability == capability:
                return cap
        return None

    def meets_requirement(self, requirement) -> bool:
        spec = self.get_capability_spec(requirement.capability)
        if not spec:
            return not requirement.required
        if requirement.min_range and spec.max_range:
            if spec.max_range < requirement.min_range:
                return False
        if requirement.min_resolution and spec.resolution:
            if spec.resolution > requirement.min_resolution:
                return False
        if requirement.min_fps and spec.fps:
            if spec.fps < requirement.min_fps:
                return False
        return True

    # ── Universal Movement Interface ───────────────────────────

    async def move_to(
        self, lat: float, lon: float, alt: float = 0.0
    ) -> CommandResult:
        """
        Move device to a WGS84 GPS position.
        GPS-less devices using odometry have their target converted automatically.
        """
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(success=False, message="No plugin instance available")

        if (
            self._node.specs
            and self._node.specs.coordinate_frame == "local"
            and self._node.local_origin
        ):
            x, y = self._gps_to_local(lat, lon)
            params = {"x": x, "y": y, "z": alt}
            logger.debug(
                f"Converted GPS ({lat}, {lon}) to local ({x:.3f}, {y:.3f}) for {self.name}"
            )
        else:
            params = {"lat": lat, "lon": lon, "alt": alt}

        envelope = CommandEnvelope(command_type=CommandType.MOVE_TO, params=params)
        return await plugin.send_command(self._node, envelope)

    async def stop(self) -> CommandResult:
        """Stop all movement immediately."""
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(success=False, message="No plugin available")
        envelope = CommandEnvelope(command_type=CommandType.STOP)
        return await plugin.send_command(self._node, envelope)

    async def return_home(self) -> CommandResult:
        """Return device to its configured home position."""
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(success=False, message="No plugin available")
        envelope = CommandEnvelope(command_type=CommandType.RETURN_HOME)
        return await plugin.send_command(self._node, envelope)

    # ── Capability Data Access ─────────────────────────────────

    async def get_gps_data(self) -> Optional[GPSData]:
        """Get current GPS data from the latest typed telemetry frame."""
        if not self.has_capability(DeviceCapability.GPS):
            return None
        frame = self._get_last_frame()
        if not frame:
            return None
        if frame.gps:
            return frame.gps
        if frame.position:
            return GPSData(
                lat=frame.position.lat,
                lon=frame.position.lon,
                alt=frame.position.alt,
            )
        return None

    async def get_lidar_scan(self) -> Optional[LidarScan]:
        """Get latest LiDAR scan from the latest typed telemetry frame."""
        if not self.has_capability(DeviceCapability.LIDAR):
            return None
        frame = self._get_last_frame()
        if frame and frame.lidar:
            return frame.lidar
        return None

    async def get_camera_feed(self) -> Optional[CameraFeed]:
        """Get camera feed info. Stream URL comes from the plugin."""
        if not self.has_capability(DeviceCapability.CAMERA):
            return None
        plugin = self._get_plugin()
        if not plugin:
            return None
        try:
            url = await plugin.get_video_stream_url(self._node)
            if not url:
                return None
            frame = self._get_last_frame()
            camera = frame.camera if frame else None
            return CameraFeed(
                stream_url=url,
                width=camera.width if camera else 0,
                height=camera.height if camera else 0,
                fps=camera.fps if camera else 0.0,
                encoding=camera.encoding if camera else "mjpeg",
                is_thermal=self.has_capability(DeviceCapability.THERMAL),
            )
        except Exception as e:
            logger.error(f"Camera feed error for {self.name}: {e}")
            return None

    async def get_battery_data(self) -> Optional[BatteryData]:
        """Get battery data from the latest typed telemetry frame."""
        if not self.has_capability(DeviceCapability.BATTERY):
            return None
        frame = self._get_last_frame()
        if frame and frame.battery:
            return frame.battery
        return None

    # ── Raw Command Access ─────────────────────────────────────

    async def send_command(
        self, capability: str, params: dict[str, Any] = {}
    ) -> CommandResult:
        """
        Send a custom command not covered by the standard movement methods.
        Use for device-specific operations declared in the manifest.
        """
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(success=False, message="No plugin available")
        envelope = CommandEnvelope(command_type=capability, params=params)
        return await plugin.send_command(self._node, envelope)

    # ── Telemetry Access ───────────────────────────────────────

    def get_telemetry_value(self, key: str, default: Any = None) -> Any:
        """Get a raw telemetry value by key (from flattened dict)."""
        return self._node.telemetry.get(key, default)

    def get_all_telemetry(self) -> dict[str, Any]:
        """Get all current telemetry as a flat dict."""
        return dict(self._node.telemetry)

    # ── Coordinate Conversion ──────────────────────────────────

    def _gps_to_local(self, lat: float, lon: float) -> tuple[float, float]:
        """
        Convert GPS coordinates to local frame metres relative to the device's origin.
        Equirectangular approximation — accurate for distances under 1km.
        """
        origin = self._node.local_origin
        if not origin:
            return lat, lon
        dlat = math.radians(lat - origin.lat)
        dlon = math.radians(lon - origin.lon)
        lat_rad = math.radians(origin.lat)
        x = dlon * EARTH_RADIUS * math.cos(lat_rad)
        y = dlat * EARTH_RADIUS
        return round(x, 4), round(y, 4)

    def local_to_gps(self, x: float, y: float) -> tuple[float, float]:
        """Convert local frame metres back to GPS coordinates."""
        origin = self._node.local_origin
        if not origin:
            return x, y
        lat_rad = math.radians(origin.lat)
        dlat = y / EARTH_RADIUS
        dlon = x / (EARTH_RADIUS * math.cos(lat_rad))
        lat = origin.lat + math.degrees(dlat)
        lon = origin.lon + math.degrees(dlon)
        return round(lat, 6), round(lon, 6)

    # ── Internal ───────────────────────────────────────────────

    def _get_plugin(self):
        return plugin_registry.get_instance(self._node.id)

    def _get_last_frame(self):
        from .node_registry import node_registry
        return node_registry.get_last_frame(self._node.id)

    def __repr__(self) -> str:
        return (
            f"DeviceProxy({self.name}, "
            f"{self.category}, "
            f"{'online' if self.is_online else 'offline'})"
        )
