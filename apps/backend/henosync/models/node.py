from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum
from datetime import datetime
import uuid


# ── Device Categories ─────────────────────────────────────────

class DeviceCategory(str, Enum):
    """
    Top-level device category.
    Add new categories here as needed — no other core changes required.
    """
    DRONE = "drone"
    PLANE = "plane"
    AGV = "agv"
    BOAT = "boat"
    ROV = "rov"
    ARM = "arm"
    UNKNOWN = "unknown"


# ── Device Capabilities ───────────────────────────────────────

class DeviceCapability(str, Enum):
    """
    Standard capability identifiers.
    Every device plugin declares which of these it supports.
    Control plugins declare which they require.
    """
    # Movement
    MOVE_2D = "move_2d"          # Ground/surface movement
    MOVE_3D = "move_3d"          # Aerial/underwater movement

    # Sensors
    GPS = "gps"                  # Global positioning
    LIDAR = "lidar"              # Laser ranging
    CAMERA = "camera"            # Visual camera
    SONAR = "sonar"              # Acoustic ranging
    IMU = "imu"                  # Inertial measurement
    THERMAL = "thermal"          # Thermal imaging

    # Actions
    HORN = "horn"                # Audible alert
    LIGHTS = "lights"            # Visual alert
    PAYLOAD = "payload"          # Payload deployment
    ARM_TOOL = "arm_tool"        # Robotic arm tool

    # Power
    BATTERY = "battery"          # Battery monitoring
    CHARGING = "charging"        # Wireless/auto charging


# ── Capability Profiles ───────────────────────────────────────

class CapabilityRequirement(BaseModel):
    """
    A control plugin's requirement for a specific capability.
    Used for capability negotiation — not just "has lidar" but
    "has lidar with at least these specs."
    """
    capability: DeviceCapability
    # Optional minimum specs — if None, any implementation accepted
    min_range: Optional[float] = None       # metres
    min_resolution: Optional[float] = None  # metres or degrees
    min_fps: Optional[float] = None         # for camera/lidar
    required: bool = True                   # False = nice to have


class CapabilitySpec(BaseModel):
    """
    A device plugin's declaration of a specific capability's specs.
    Used by the core to match devices to control plugin requirements.
    """
    capability: DeviceCapability
    # Actual hardware specs
    max_range: Optional[float] = None
    resolution: Optional[float] = None
    fps: Optional[float] = None
    fov: Optional[float] = None             # field of view degrees
    dimensions: Optional[int] = None        # 2D or 3D for lidar
    notes: Optional[str] = None             # free text spec notes


# ── Device Specifications ─────────────────────────────────────

class DeviceSpecs(BaseModel):
    """
    Physical and operational specifications of a device.
    Declared by the device plugin.
    Used by control plugins to make intelligent decisions.
    """
    category: DeviceCategory = DeviceCategory.UNKNOWN
    capabilities: list[CapabilitySpec] = []

    # Physical
    weight_kg: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None

    # Operational
    max_speed_ms: Optional[float] = None    # metres per second
    max_range_m: Optional[float] = None     # operational range
    max_altitude_m: Optional[float] = None  # for aerial devices
    min_altitude_m: Optional[float] = None
    battery_capacity_wh: Optional[float] = None
    endurance_minutes: Optional[float] = None

    # Navigation
    has_gps: bool = False
    uses_odometry: bool = False
    coordinate_frame: str = "gps"           # "gps" or "local"
    # If coordinate_frame is "local", home_position is the GPS origin
    # All odometry positions are converted relative to this origin


# ── Coordinate System ─────────────────────────────────────────

class Position(BaseModel):
    """
    Universal position in WGS84 GPS coordinates.
    ALL positions in the system use this format regardless of device.
    Device plugins convert from their native frame internally.
    """
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0            # metres above sea level
    heading: Optional[float] = None  # degrees 0-360, None if unknown
    accuracy: Optional[float] = None  # metres, None if unknown


class LocalOrigin(BaseModel):
    """
    GPS origin for devices without GPS.
    Set by operator when adding a non-GPS device.
    All odometry positions converted relative to this point.
    """
    lat: float
    lon: float
    alt: float = 0.0


# ── Capability Data Schemas ───────────────────────────────────
# Standard data formats for each capability.
# ALL device plugins MUST conform to these schemas when
# reporting capability data. No exceptions.
# Convert from native hardware format inside the plugin.

class GPSData(BaseModel):
    """Standard GPS data format."""
    lat: float
    lon: float
    alt: float
    accuracy: float = 0.0
    fix_type: str = "none"      # "none", "2d", "3d", "rtk"
    satellites: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LidarPoint(BaseModel):
    x: float
    y: float
    z: float = 0.0
    intensity: Optional[float] = None


class LidarScan(BaseModel):
    """Standard LiDAR scan data format."""
    points: list[LidarPoint] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    frame_id: str = "lidar"
    range_min: float = 0.0
    range_max: float = 0.0
    scan_rate_hz: Optional[float] = None
    dimensions: int = 2         # 2 for 2D lidar, 3 for 3D


class CameraFeed(BaseModel):
    """Standard camera feed data format."""
    stream_url: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    encoding: str = "mjpeg"     # "mjpeg", "h264", "rtsp"
    is_thermal: bool = False


class BatteryData(BaseModel):
    """Standard battery data format."""
    percentage: float           # 0.0 - 100.0
    voltage: Optional[float] = None
    current: Optional[float] = None
    temperature: Optional[float] = None
    time_remaining_minutes: Optional[float] = None
    is_charging: bool = False


# ── Node Status ───────────────────────────────────────────────

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


# ── Node Model ────────────────────────────────────────────────

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


class NodeCreate(BaseModel):
    name: str
    plugin_id: str
    config: dict[str, Any] = {}


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None