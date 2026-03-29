import asyncio
import math
import logging
from typing import Optional, Any
from datetime import datetime, timezone
from ..models import (
    Node, NodeStatus, Position, DeviceCategory,
    DeviceCapability, DeviceSpecs, CapabilitySpec,
    GPSData, LidarScan, CameraFeed, BatteryData,
    CommandResult, LocalOrigin
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
    - Capability data retrieval in standard formats
    - Command dispatch through the device plugin
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
    def is_online(self) -> bool:
        return self._node.status == NodeStatus.ONLINE

    @property
    def is_available(self) -> bool:
        """Available means online and not reserved by another operation."""
        return self.is_online

    @property
    def position(self) -> Position:
        return self._node.position

    @property
    def battery_percent(self) -> Optional[float]:
        return self._node.battery_percent

    # ── Capability Checks ──────────────────────────────────────

    def has_capability(self, capability: DeviceCapability) -> bool:
        """Check if this device has a specific capability."""
        if not self._node.specs:
            return False
        return any(
            c.capability == capability
            for c in self._node.specs.capabilities
        )

    def get_capability_spec(
        self,
        capability: DeviceCapability
    ) -> Optional[CapabilitySpec]:
        """Get the spec for a specific capability."""
        if not self._node.specs:
            return None
        for cap in self._node.specs.capabilities:
            if cap.capability == capability:
                return cap
        return None

    def meets_requirement(self, requirement) -> bool:
        """
        Check if this device meets a CapabilityRequirement.
        Used by capability negotiation system.
        """
        spec = self.get_capability_spec(requirement.capability)
        if not spec:
            return not requirement.required

        # Check minimum specs if declared
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
        self,
        lat: float,
        lon: float,
        alt: float = 0.0
    ) -> CommandResult:
        """
        Move device to a WGS84 GPS position.

        Works for ALL device types regardless of their native
        coordinate system. GPS-less devices using odometry
        have their target position converted to local frame
        automatically using their configured local origin.

        Args:
            lat: Target latitude (WGS84)
            lon: Target longitude (WGS84)
            alt: Target altitude in metres above sea level
        """
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(
                success=False,
                message="No plugin instance available"
            )

        # Convert coordinates if device uses local frame
        if (
            self._node.specs and
            self._node.specs.coordinate_frame == "local" and
            self._node.local_origin
        ):
            x, y = self._gps_to_local(lat, lon)
            params = {"x": x, "y": y, "z": alt}
            logger.debug(
                f"Converted GPS ({lat}, {lon}) to local "
                f"({x:.3f}, {y:.3f}) for {self.name}"
            )
        else:
            params = {"lat": lat, "lon": lon, "alt": alt}

        return await plugin.send_command(
            self._node, "move_to", params
        )

    async def stop(self) -> CommandResult:
        """Stop all movement immediately."""
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(
                success=False, message="No plugin available"
            )
        return await plugin.send_command(self._node, "stop", {})

    async def return_home(self) -> CommandResult:
        """Return device to its configured home position."""
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(
                success=False, message="No plugin available"
            )
        return await plugin.send_command(
            self._node, "return_home", {}
        )

    # ── Capability Data Access ─────────────────────────────────

    async def get_gps_data(self) -> Optional[GPSData]:
        """
        Get current GPS data in standard format.
        Returns None if device has no GPS capability.
        """
        if not self.has_capability(DeviceCapability.GPS):
            return None

        telemetry = self._node.telemetry
        if not telemetry:
            return None

        try:
            return GPSData(
                lat=telemetry.get("lat", 0.0),
                lon=telemetry.get("lon", 0.0),
                alt=telemetry.get("alt", 0.0),
                accuracy=telemetry.get("gps_accuracy", 0.0),
                fix_type=telemetry.get("gps_fix_type", "unknown"),
                satellites=telemetry.get("satellites", 0)
            )
        except Exception as e:
            logger.error(f"GPS data error for {self.name}: {e}")
            return None

    async def get_lidar_scan(self) -> Optional[LidarScan]:
        """
        Get latest LiDAR scan in standard format.
        Returns None if device has no LiDAR capability.
        Device plugin must populate 'lidar_scan' in telemetry.
        """
        if not self.has_capability(DeviceCapability.LIDAR):
            return None

        scan_data = self._node.telemetry.get("lidar_scan")
        if not scan_data:
            return None

        try:
            return LidarScan(**scan_data)
        except Exception as e:
            logger.error(f"LiDAR data error for {self.name}: {e}")
            return None

    async def get_camera_feed(self) -> Optional[CameraFeed]:
        """
        Get camera feed info in standard format.
        Returns None if device has no camera capability.
        """
        if not self.has_capability(DeviceCapability.CAMERA):
            return None

        plugin = self._get_plugin()
        if not plugin:
            return None

        try:
            url = await plugin.get_video_stream_url(self._node)
            if not url:
                return None

            return CameraFeed(
                stream_url=url,
                width=self._node.telemetry.get("camera_width", 0),
                height=self._node.telemetry.get("camera_height", 0),
                fps=self._node.telemetry.get("camera_fps", 0.0),
                encoding=self._node.telemetry.get(
                    "camera_encoding", "mjpeg"
                ),
                is_thermal=self.has_capability(DeviceCapability.THERMAL)
            )
        except Exception as e:
            logger.error(f"Camera feed error for {self.name}: {e}")
            return None

    async def get_battery_data(self) -> Optional[BatteryData]:
        """Get battery data in standard format."""
        if not self.has_capability(DeviceCapability.BATTERY):
            return None

        telemetry = self._node.telemetry
        try:
            return BatteryData(
                percentage=telemetry.get("battery_percent", 0.0),
                voltage=telemetry.get("battery_voltage"),
                current=telemetry.get("battery_current"),
                temperature=telemetry.get("battery_temp"),
                time_remaining_minutes=telemetry.get(
                    "battery_time_remaining"
                ),
                is_charging=telemetry.get("is_charging", False)
            )
        except Exception as e:
            logger.error(f"Battery data error for {self.name}: {e}")
            return None

    # ── Raw Command Access ─────────────────────────────────────

    async def send_command(
        self,
        capability: str,
        params: dict[str, Any] = {}
    ) -> CommandResult:
        """
        Send a raw command to the device.
        Use this for device-specific operations not covered
        by the standard capability data methods above.
        """
        plugin = self._get_plugin()
        if not plugin:
            return CommandResult(
                success=False, message="No plugin available"
            )
        return await plugin.send_command(
            self._node, capability, params
        )

    # ── Telemetry Access ───────────────────────────────────────

    def get_telemetry_value(
        self,
        key: str,
        default: Any = None
    ) -> Any:
        """Get a raw telemetry value by key."""
        return self._node.telemetry.get(key, default)

    def get_all_telemetry(self) -> dict[str, Any]:
        """Get all current telemetry values."""
        return dict(self._node.telemetry)

    # ── Coordinate Conversion ──────────────────────────────────

    def _gps_to_local(
        self,
        lat: float,
        lon: float
    ) -> tuple[float, float]:
        """
        Convert GPS coordinates to local frame metres
        relative to the device's configured local origin.

        Uses equirectangular approximation — accurate for
        distances under 1km typical in robot operations.
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

    def local_to_gps(
        self,
        x: float,
        y: float
    ) -> tuple[float, float]:
        """
        Convert local frame metres back to GPS coordinates.
        Inverse of _gps_to_local.
        Useful for reporting device position in universal format.
        """
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
        """Get the plugin instance for this device."""
        return plugin_registry.get_instance(self._node.id)

    def __repr__(self) -> str:
        return (
            f"DeviceProxy({self.name}, "
            f"{self.category}, "
            f"{'online' if self.is_online else 'offline'})"
        )