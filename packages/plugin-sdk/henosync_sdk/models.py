"""
Henosync Plugin SDK — Models
=============================
Canonical definitions for all types shared between the backend and plugins.
The backend imports from here. Plugin developers import from henosync_sdk.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


# ── Device Categories ─────────────────────────────────────────────────────────

class DeviceCategory(str, Enum):
    DRONE = "drone"
    PLANE = "plane"
    AGV = "agv"
    BOAT = "boat"
    ROV = "rov"
    ARM = "arm"
    LEGGED = "legged"
    VTOL = "vtol"
    TRACKED = "tracked"
    STATIC = "static"
    UNKNOWN = "unknown"


# ── Device Capabilities ───────────────────────────────────────────────────────

class DeviceCapability(str, Enum):
    MOVE_2D = "move_2d"
    MOVE_3D = "move_3d"
    GPS = "gps"
    LIDAR = "lidar"
    CAMERA = "camera"
    SONAR = "sonar"
    IMU = "imu"
    THERMAL = "thermal"
    HORN = "horn"
    LIGHTS = "lights"
    PAYLOAD = "payload"
    ARM_TOOL = "arm_tool"
    BATTERY = "battery"
    CHARGING = "charging"


# ── Capability Profiles ───────────────────────────────────────────────────────

class CapabilityRequirement(BaseModel):
    """A control plugin's requirement for a specific capability."""
    capability: DeviceCapability
    min_range: Optional[float] = None
    min_resolution: Optional[float] = None
    min_fps: Optional[float] = None
    required: bool = True


class CapabilitySpec(BaseModel):
    """A device plugin's declaration of a specific capability's specs."""
    capability: DeviceCapability
    max_range: Optional[float] = None
    resolution: Optional[float] = None
    fps: Optional[float] = None
    fov: Optional[float] = None
    dimensions: Optional[int] = None
    notes: Optional[str] = None


# ── Device Specifications ─────────────────────────────────────────────────────

class DeviceSpecs(BaseModel):
    """
    Physical and operational specifications declared by the device plugin.
    Set node.specs in connect() — required for capability matching.
    """
    category: DeviceCategory = DeviceCategory.UNKNOWN
    capabilities: list[CapabilitySpec] = []
    weight_kg: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    max_speed_ms: Optional[float] = None
    max_range_m: Optional[float] = None
    max_altitude_m: Optional[float] = None
    min_altitude_m: Optional[float] = None
    battery_capacity_wh: Optional[float] = None
    endurance_minutes: Optional[float] = None
    has_gps: bool = False
    uses_odometry: bool = False
    coordinate_frame: str = "gps"


# ── Coordinate System ─────────────────────────────────────────────────────────

class Position(BaseModel):
    """Universal position in WGS84 GPS coordinates."""
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0
    heading: Optional[float] = None
    accuracy: Optional[float] = None


class LocalOrigin(BaseModel):
    """GPS origin for devices without GPS (odometry-based)."""
    lat: float
    lon: float
    alt: float = 0.0


# ── Capability Data Schemas ───────────────────────────────────────────────────

class GPSData(BaseModel):
    lat: float
    lon: float
    alt: float
    accuracy: float = 0.0
    fix_type: str = "none"
    satellites: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IMUData(BaseModel):
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    angular_velocity_x: float = 0.0
    angular_velocity_y: float = 0.0
    angular_velocity_z: float = 0.0


class LidarPoint(BaseModel):
    x: float
    y: float
    z: float = 0.0
    intensity: Optional[float] = None


class LidarScan(BaseModel):
    points: list[LidarPoint] = []
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    frame_id: str = "lidar"
    range_min: float = 0.0
    range_max: float = 0.0
    scan_rate_hz: Optional[float] = None
    dimensions: int = 2


class CameraFeed(BaseModel):
    stream_url: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    encoding: str = "mjpeg"
    is_thermal: bool = False


class BatteryData(BaseModel):
    percentage: float
    voltage: Optional[float] = None
    current: Optional[float] = None
    temperature: Optional[float] = None
    time_remaining_minutes: Optional[float] = None
    is_charging: bool = False


# ── Node Status ───────────────────────────────────────────────────────────────

class NodeStatus(str, Enum):
    CONNECTING = "connecting"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"


class NodeCapability(BaseModel):
    """A named action capability exposed by a device plugin."""
    id: str
    label: str
    params: list[str] = []
    destructive: bool = False


# ── Node ─────────────────────────────────────────────────────────────────────

class Node(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    plugin_id: str
    status: NodeStatus = NodeStatus.OFFLINE
    position: Position = Field(default_factory=Position)
    battery_percent: Optional[float] = None
    signal_strength: Optional[float] = None
    capabilities: list[NodeCapability] = []
    telemetry: dict[str, Any] = {}
    last_seen: Optional[datetime] = None
    home_position: Optional[Position] = None
    local_origin: Optional[LocalOrigin] = None
    config: dict[str, Any] = {}
    specs: Optional[DeviceSpecs] = None


# ── Commands ──────────────────────────────────────────────────────────────────

class CommandType(str, Enum):
    """Standard command types. Use these in cmd_* method overrides."""
    MOVE_TO = "move_to"
    STOP = "stop"
    RETURN_HOME = "return_home"
    TAKE_PHOTO = "take_photo"
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"


class CommandEnvelope(BaseModel):
    """
    Typed command wrapper. All send_command calls use this.

    command_id: unique ID for tracking async completion via context.command_completed()
    command_type: use CommandType constants for standard commands, or any string for custom
    params: command parameters (validated by cmd_* method implementations)
    """
    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command_type: str
    params: dict[str, Any] = {}


# ── Telemetry ─────────────────────────────────────────────────────────────────

class TelemetryFrame(BaseModel):
    """
    Structured telemetry from a device plugin.

    Use typed fields (position, battery, imu, etc.) where possible.
    Use custom{} for plugin-specific data not covered by standard fields.
    """
    node_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence_number: int = 0

    # Standard typed fields — set these instead of using custom{}
    position: Optional[Position] = None
    battery: Optional[BatteryData] = None
    imu: Optional[IMUData] = None
    gps: Optional[GPSData] = None
    lidar: Optional[LidarScan] = None
    camera: Optional[CameraFeed] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    signal_strength: Optional[float] = None
    status_text: Optional[str] = None

    # Escape hatch for plugin-specific data not covered above
    custom: dict[str, Any] = {}

    def to_values_dict(self) -> dict[str, Any]:
        """
        Flatten typed fields to a string-keyed dict.
        Used for WebSocket broadcast and backward-compatible node.telemetry.
        """
        d: dict[str, Any] = dict(self.custom)

        if self.position:
            d["lat"] = self.position.lat
            d["lon"] = self.position.lon
            d["alt"] = self.position.alt
            if self.position.heading is not None:
                d.setdefault("heading", self.position.heading)

        if self.battery:
            d["battery_percent"] = self.battery.percentage
            if self.battery.voltage is not None:
                d["battery_voltage"] = self.battery.voltage
            if self.battery.current is not None:
                d["battery_current"] = self.battery.current
            d["is_charging"] = self.battery.is_charging
            if self.battery.time_remaining_minutes is not None:
                d["battery_time_remaining"] = self.battery.time_remaining_minutes

        if self.imu:
            d["roll"] = self.imu.roll
            d["pitch"] = self.imu.pitch
            d["yaw"] = self.imu.yaw
            d.setdefault("heading", self.imu.yaw)

        if self.gps:
            d.setdefault("lat", self.gps.lat)
            d.setdefault("lon", self.gps.lon)
            d.setdefault("alt", self.gps.alt)
            d["gps_accuracy"] = self.gps.accuracy
            d["gps_fix_type"] = self.gps.fix_type
            d["satellites"] = self.gps.satellites

        if self.speed is not None:
            d["speed"] = self.speed
        if self.heading is not None:
            d.setdefault("heading", self.heading)
        if self.signal_strength is not None:
            d["signal_strength"] = self.signal_strength
        if self.status_text is not None:
            d["status_text"] = self.status_text

        return d


class CommandResult(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = {}


# ── Event Severity ────────────────────────────────────────────────────────────

class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ── Plugin Context ────────────────────────────────────────────────────────────

class NodePluginContext:
    """
    Injected into your plugin via connect(). Store as self._context.

    Provides backend services so plugins can push events and signal
    command completion without importing from the backend directly.
    """

    def __init__(
        self,
        node_id: str,
        emit_event_fn: Callable,
        command_completed_fn: Callable,
    ):
        self._node_id = node_id
        self._emit_event_fn = emit_event_fn
        self._command_completed_fn = command_completed_fn

    async def emit_event(
        self,
        title: str,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
    ) -> None:
        """Emit a system event visible to the operator in the events panel."""
        await self._emit_event_fn(title, message, severity, self._node_id)

    async def command_completed(
        self,
        command_id: str,
        success: bool,
        message: str = "",
    ) -> None:
        """
        Signal that an async command has finished executing.

        Call this from telemetry_stream or a background task when the robot
        confirms it has reached a destination or completed an action.
        command_id comes from the CommandEnvelope passed to send_command.
        """
        await self._command_completed_fn(command_id, success, message)
