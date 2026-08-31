"""
Auto Navigate — autonomous navigation control plugin.

Executes a sequence of navigation steps against every assigned device.
Each step targets a map marker or zone and runs to completion before
the next step begins.

Multi-device: for MOVE_TO_MARKER/MOVE_TO_ZONE, the target is resolved once
per step and every assigned device navigates there concurrently (asyncio.gather
in _run_on_devices) — one shared target, all robots start together, not a
per-device queue. A device can also be added to a running operation via
operation_manager.recruit_device_into_operation() (operator-triggered only —
there's no automatic join when a new device connects); on_device_joined()
sends it toward whatever target is currently active. get_status() reports
per-device status text (self._device_status), since with concurrent devices
a single shared status string would just have them racing to overwrite it.

Step types
----------
MOVE_TO_MARKER   Navigate to a specific map marker position.
MOVE_TO_ZONE     Navigate to the centroid of a zone.
AREA_COVERAGE    Sweep a zone with a lawnmower pattern at a set spacing.
PERIMETER_PATROL Follow the boundary of a zone for a set number of laps.

MOVE_TO_MARKER and MOVE_TO_ZONE go through _go_to_waypoint(), which prefers
the device's own cmd_move_to() (via device.move_to()) when implemented —
e.g. turtlebot3, which drives with real heading from /odom — and only falls
back to _navigate_to(), a closed-loop controller over the generic cmd_vel
contract teleop uses, for devices with no cmd_move_to (e.g. ue-sim).
_navigate_to() estimates heading from GPS course-over-ground (consecutive
fixes while moving) instead, since it predates any device reporting real
heading.

Obstacle handling in the _navigate_to() fallback path is reactive-stop only,
not routing-around: it reacts to CommandResult.data["reason"] == "obstacle"
on a blocked cmd_vel by waiting for the path to clear
(OBSTACLE_BLOCKED_TIMEOUT_S) rather than steering around it, and start()
warns once if an assigned device has no LiDAR capability. As of 2026-08-23
this is dead code in practice — it was built against a since-removed
generic ros2-diffdrive plugin that set that reason; no currently-loaded
device plugin (ue-sim, turtlebot3) does. The move_to() path (turtlebot3) has
no obstacle detection of any kind.

AREA_COVERAGE splits the target zone into as many parallel strips as there
are assigned devices (captured once when the step starts — a device that
joins mid-sweep via on_device_joined is not folded into a re-split), and
generates a boustrophedon (back-and-forth) sweep path per strip via
_generate_coverage_paths(). Strips are split by equal AREA, not equal
height/count (_equal_area_band_bounds) — an equal-height split badly
unbalances coverage time on any non-rectangular zone, since a short/wide
band and a tall/narrow band can hold very different amounts of actual zone
area. Strip/line clipping to the zone boundary is sampling-based
(_inside_extent), not exact polygon-edge intersection, so a sharply
concave zone can get a slightly optimistic or stair-stepped sweep near
inward corners — acceptable for the roughly-convex zones an operator draws
in practice. Each device runs its own path independently
(_run_coverage_path) and returns to the GPS position it was at when the
step began. The inter-robot separation guard (_collision_guard) still
applies during coverage — since there's no longer one shared target, it
tracks each device's current waypoint in self._device_target instead of
self._current_target.

PERIMETER_PATROL is still unimplemented — deferred.
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from henosync_sdk import (
    CapabilityRequirement,
    ControlPlugin,
    DeviceCapability,
    DeviceCategory,
    EventSeverity,
    OperationState,
    OperationStatus,
    UIContribution,
)

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6371000.0

# Go-to-waypoint controller tuning.
#
# MIN_MOVE_FOR_HEADING_M, MAX_ANGULAR, and MIN_ALIGNMENT_FRACTION are coupled:
# the robot's minimum achievable turning circle (governed by MIN_ALIGNMENT_FRACTION's
# crawl speed vs MAX_ANGULAR's turn rate) must stay larger than MIN_MOVE_FOR_HEADING_M,
# or the heading estimate can never refresh while turning and the robot loops forever
# on a stale heading. These defaults leave comfortable margin for a 1 m/s / 45deg/s-class
# vehicle; a much tighter-turning real robot may need MIN_MOVE_FOR_HEADING_M lowered further.
ARRIVAL_TOLERANCE_M = 1.5        # close enough to the target to stop
MIN_MOVE_FOR_HEADING_M = 0.3     # distance travelled before re-estimating heading
MAX_ANGULAR = 0.6                # cap on turn authority — wider turns keep heading estimates fresh
MIN_ALIGNMENT_FRACTION = 0.4     # never fully stop while correcting heading — course-over-ground
                                  # heading estimation requires movement, so a hard "turn in place"
                                  # (linear=0) would freeze the heading estimate and never recover
SLOWDOWN_RADIUS_M = 3.0          # start slowing down within this radius of target
CONTROL_PERIOD_S = 0.5           # how often to recompute and resend cmd_vel
DRIVE_LINEAR = 0.6               # normalized forward speed while well-aligned with the target
PROBE_LINEAR = 0.3               # normalized speed while establishing initial heading
WAYPOINT_TIMEOUT_S = 120.0       # give up on a single waypoint after this long
OBSTACLE_BLOCKED_TIMEOUT_S = 15.0  # give up if an obstacle doesn't clear within this long

# Inter-robot collision guard (see _collision_guard()) — independent of the
# per-device controller above, applies to every device regardless of which
# controller path (move_to() or cmd_vel) it's using.
MIN_SEPARATION_M = 2.0           # yield if closer than this to another navigating robot
SEPARATION_CHECK_PERIOD_S = 0.5  # how often to check pairwise distances

# Coverage path generation (_generate_coverage_paths) — independent of the
# per-waypoint controller tuning above.
CIRCLE_APPROXIMATION_SIDES = 32  # regular polygon used to approximate circle zones
MAX_COVERAGE_SAMPLES = 20000     # total scanline sample budget across all strips —
                                  # sampling is coarsened (not failed) if a request
                                  # would exceed this, same spirit as mission_engine's
                                  # MAX_ITERATIONS safety cap
AREA_PROFILE_Y_SAMPLES = 150     # y-slices used to build the cumulative-area profile
                                  # that _equal_area_band_bounds() splits on
AREA_PROFILE_X_SAMPLES = 80      # x-samples per y-slice when estimating width(y) for
                                  # that profile — a one-time fixed cost per step start,
                                  # independent of zone size or spacing, so no need for
                                  # MAX_COVERAGE_SAMPLES-style coarsening here


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two GPS points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing from point 1 to point 2, in degrees (0=N, 90=E)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _angle_diff_deg(a: float, b: float) -> float:
    """Smallest signed difference a-b in degrees, range (-180, 180]."""
    return (a - b + 180) % 360 - 180


# ── Coverage path geometry (AREA_COVERAGE) ──────────────────────────────────────
#
# All of this works in a local, flat XY metres frame (equirectangular
# approximation, same as device_proxy._gps_to_local) rather than directly in
# lat/lon, so ordinary Euclidean rotation/rayscan math applies. Coordinates
# only touch lat/lon at the boundary: _zone_polygon_and_origin() converts in,
# _generate_coverage_paths() converts back out.

def _local_xy(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """GPS -> local (east, north) metres relative to an origin."""
    lat_rad = math.radians(origin_lat)
    dlat = math.radians(lat - origin_lat)
    dlon = math.radians(lon - origin_lon)
    x = dlon * EARTH_RADIUS_M * math.cos(lat_rad)
    y = dlat * EARTH_RADIUS_M
    return x, y


def _xy_to_latlon(x: float, y: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """Local (east, north) metres -> GPS, relative to an origin."""
    lat_rad = math.radians(origin_lat)
    dlat = y / EARTH_RADIUS_M
    dlon = x / (EARTH_RADIUS_M * math.cos(lat_rad))
    return origin_lat + math.degrees(dlat), origin_lon + math.degrees(dlon)


def _rotate(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    """Rotate (x, y) by -angle_deg — the direction angle_deg (0=east, 90=north)
    maps onto +x' in the result, so sweep lines along that direction become
    lines of constant y' in the rotated frame."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return x * cos_t + y * sin_t, -x * sin_t + y * cos_t


def _unrotate(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    """Inverse of _rotate — rotate by +angle_deg back to the original frame."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return x * cos_t - y * sin_t, x * sin_t + y * cos_t


def _point_in_polygon_xy(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test in local XY metres."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersect:
                inside = not inside
    return inside


def _zone_polygon_and_origin(zone) -> tuple[list[tuple[float, float]], float, float]:
    """
    Zone geometry as a local-XY polygon plus the GPS origin it's relative to.
    Circle zones are approximated as a CIRCLE_APPROXIMATION_SIDES-gon.
    """
    if zone.center is not None and zone.radius_m is not None:
        origin_lat, origin_lon = zone.center.lat, zone.center.lon
        polygon = [
            (
                zone.radius_m * math.cos(2 * math.pi * i / CIRCLE_APPROXIMATION_SIDES),
                zone.radius_m * math.sin(2 * math.pi * i / CIRCLE_APPROXIMATION_SIDES),
            )
            for i in range(CIRCLE_APPROXIMATION_SIDES)
        ]
        return polygon, origin_lat, origin_lon

    if zone.points and len(zone.points) >= 3:
        origin_lat = sum(p.lat for p in zone.points) / len(zone.points)
        origin_lon = sum(p.lon for p in zone.points) / len(zone.points)
        polygon = [_local_xy(p.lat, p.lon, origin_lat, origin_lon) for p in zone.points]
        return polygon, origin_lat, origin_lon

    raise ValueError(f"Zone has no usable geometry: {getattr(zone, 'name', zone)}")


def _inside_extent(
    y: float, x_min: float, x_max: float, num_samples: int, polygon: list[tuple[float, float]]
) -> Optional[tuple[float, float]]:
    """
    Sample a scan line at height y across [x_min, x_max] and return the
    (min, max) x of samples that land inside `polygon` — the outer extent
    of one pass, not a per-gap breakdown. A concave zone with a real gap
    along this line still gets one straight-through pass; see
    _generate_coverage_paths' docstring.
    """
    step = (x_max - x_min) / (num_samples - 1) if num_samples > 1 else x_max - x_min
    inside_xs = [
        x for i in range(num_samples)
        if _point_in_polygon_xy(x := x_min + i * step, y, polygon)
    ]
    if not inside_xs:
        return None
    return min(inside_xs), max(inside_xs)


def _width_at_y(
    y: float, x_min: float, x_max: float, polygon: list[tuple[float, float]],
    num_samples: int = AREA_PROFILE_X_SAMPLES,
) -> float:
    """
    Area-weighted width estimate at height y: the fraction of x samples
    landing inside `polygon`, scaled by the full x extent. Deliberately
    different from _inside_extent()'s outer span — that's the right notion
    for "where does one sweep pass run", but for area-balancing a concave
    zone's real gaps must count as NOT covered, or a band that's mostly
    empty space would be credited as if it were solid.
    """
    step = (x_max - x_min) / (num_samples - 1) if num_samples > 1 else x_max - x_min
    inside_count = sum(
        1 for i in range(num_samples)
        if _point_in_polygon_xy(x_min + i * step, y, polygon)
    )
    return (inside_count / num_samples) * (x_max - x_min)


def _equal_area_band_bounds(
    polygon: list[tuple[float, float]], num_robots: int,
    x_min: float, x_max: float, y_min: float, y_max: float,
) -> list[tuple[float, float]]:
    """
    Split [y_min, y_max] into `num_robots` bands of equal POLYGON AREA, not
    equal height. Equal-height bands badly unbalance coverage time on any
    non-rectangular zone — a short/wide band and a tall/narrow band can
    hold very different amounts of actual zone area, so some robots would
    finish in a fraction of the time others take. Builds a cumulative
    area-vs-y profile by sampling _width_at_y() at AREA_PROFILE_Y_SAMPLES
    heights (trapezoidal integration), then finds the y at each 1/num_robots
    fraction of total area via linear interpolation on that profile.

    A pointed region (e.g. a triangular corner) can still end up as a tall,
    narrow band to make up its equal share of area — which can in turn
    produce a very short or empty sweep path for whichever robot gets it.
    That's an inherent limit of a 1D (horizontal-band) area split, not a
    bug: _run_coverage_path() already handles an empty path gracefully.
    """
    y_step = (y_max - y_min) / AREA_PROFILE_Y_SAMPLES
    widths = [
        _width_at_y(y_min + i * y_step, x_min, x_max, polygon)
        for i in range(AREA_PROFILE_Y_SAMPLES + 1)
    ]

    cumulative = [0.0]
    for i in range(1, len(widths)):
        cumulative.append(cumulative[-1] + (widths[i - 1] + widths[i]) / 2 * y_step)

    total_area = cumulative[-1]
    if total_area <= 0:
        raise ValueError("Zone has no area")

    def y_at_area(target: float) -> float:
        for i in range(1, len(cumulative)):
            if cumulative[i] >= target:
                c0, c1 = cumulative[i - 1], cumulative[i]
                frac = 0.0 if c1 == c0 else (target - c0) / (c1 - c0)
                return y_min + (i - 1 + frac) * y_step
        return y_max

    boundaries = (
        [y_min]
        + [y_at_area(k * total_area / num_robots) for k in range(1, num_robots)]
        + [y_max]
    )
    return list(zip(boundaries[:-1], boundaries[1:]))


def _generate_coverage_paths(
    zone, num_robots: int, spacing_m: float, angle_deg: float
) -> list[list[tuple[float, float]]]:
    """
    Partition `zone` into `num_robots` parallel strips of equal AREA
    (perpendicular to angle_deg — see _equal_area_band_bounds()) and
    generate a boustrophedon sweep path within each strip, clipped to the
    zone boundary. Returns one waypoint list per robot, in the same order
    bands are assigned (index i runs from the angle_deg+90 side of the
    zone).
    """
    if num_robots < 1:
        raise ValueError("No robots assigned")
    if spacing_m <= 0:
        raise ValueError("Coverage spacing must be positive")

    polygon, origin_lat, origin_lon = _zone_polygon_and_origin(zone)
    rotated = [_rotate(x, y, angle_deg) for x, y in polygon]

    x_min = min(p[0] for p in rotated)
    x_max = max(p[0] for p in rotated)
    y_min = min(p[1] for p in rotated)
    y_max = max(p[1] for p in rotated)

    width, height = x_max - x_min, y_max - y_min
    if width <= 0 or height <= 0:
        raise ValueError("Zone is too small to cover")

    band_bounds = _equal_area_band_bounds(rotated, num_robots, x_min, x_max, y_min, y_max)

    sample_step = max(spacing_m / 4.0, 0.25)
    num_samples_per_line = min(2000, max(2, int(width / sample_step) + 1))

    # Bands no longer share one height, so line count is worked out per band
    # up front purely to size the sample budget check below.
    per_band_lines = [max(1, int((b_max - b_min) / spacing_m)) for b_min, b_max in band_bounds]
    total_samples = sum(per_band_lines) * num_samples_per_line
    if total_samples > MAX_COVERAGE_SAMPLES:
        # Coarsen sampling to stay within budget rather than fail outright.
        scale = math.sqrt(total_samples / MAX_COVERAGE_SAMPLES)
        sample_step *= scale
        num_samples_per_line = min(2000, max(2, int(width / sample_step) + 1))

    paths: list[list[tuple[float, float]]] = []
    for band_y_min, band_y_max in band_bounds:
        num_lines = max(1, int((band_y_max - band_y_min) / spacing_m))

        if num_lines == 1:
            line_ys = [(band_y_min + band_y_max) / 2.0]
        else:
            line_step = (band_y_max - band_y_min) / num_lines
            line_ys = [band_y_min + line_step * (i + 0.5) for i in range(num_lines)]

        waypoints_xy: list[tuple[float, float]] = []
        for line_idx, y in enumerate(line_ys):
            segment = _inside_extent(y, x_min, x_max, num_samples_per_line, rotated)
            if segment is None:
                continue
            seg_x_min, seg_x_max = segment
            left_to_right = (line_idx % 2 == 0)
            start_x, end_x = (seg_x_min, seg_x_max) if left_to_right else (seg_x_max, seg_x_min)
            waypoints_xy.append((start_x, y))
            waypoints_xy.append((end_x, y))

        path = [
            _xy_to_latlon(*_unrotate(x, y, angle_deg), origin_lat, origin_lon)
            for x, y in waypoints_xy
        ]
        paths.append(path)

    return paths


# ── Step types ─────────────────────────────────────────────────────────────────

class StepType(str, Enum):
    MOVE_TO_MARKER   = "move_to_marker"
    MOVE_TO_ZONE     = "move_to_zone"
    AREA_COVERAGE    = "area_coverage"
    PERIMETER_PATROL = "perimeter_patrol"


@dataclass
class NavigationStep:
    """One item in the operation's step sequence."""
    step_type: StepType

    # Target — set one depending on step type
    marker_id: Optional[str] = None   # MOVE_TO_MARKER
    zone_id:   Optional[str] = None   # MOVE_TO_ZONE, AREA_COVERAGE, PERIMETER_PATROL

    # Common parameters
    speed_ms: float = 1.0             # travel speed in m/s

    # AREA_COVERAGE parameters
    coverage_spacing_m: float = 5.0   # distance between sweep lanes in metres
    coverage_angle_deg: float = 0.0   # sweep direction (0 = east, 90 = north)

    # PERIMETER_PATROL parameters
    patrol_laps: int = 1              # number of times to loop the boundary


# ── Plugin ─────────────────────────────────────────────────────────────────────

class AutoNavigatePlugin(ControlPlugin):
    """
    Autonomous navigation control plugin.

    Reads a list of NavigationStep objects from self._config["steps"],
    executes them in sequence on each assigned device, then completes.
    """

    PLUGIN_ID           = "auto-navigate"
    PLUGIN_NAME         = "Auto Navigate"
    PLUGIN_VERSION      = "0.1.0"
    PLUGIN_AUTHOR       = "Henosync Team — Monash University"
    OPERATION_NAME      = "Auto Navigate"
    OPERATION_DESCRIPTION = "Sequential autonomous navigation: move, coverage, patrol"

    REQUIRED_CAPABILITIES: list[CapabilityRequirement] = [
        CapabilityRequirement(capability=DeviceCapability.GPS, required=True),
        CapabilityRequirement(capability=DeviceCapability.MOVE_2D, required=True),
    ]

    SUPPORTED_CATEGORIES: list[DeviceCategory] = [
        DeviceCategory.AGV,
        DeviceCategory.DRONE,
    ]

    PRIORITY: int = 10

    def __init__(self) -> None:
        super().__init__()
        self._state: OperationState = OperationState.IDLE
        self._status_text: str = ""
        self._current_step: int = 0
        self._total_steps: int = 0
        # Devices currently mid-navigation (device_id -> DeviceProxy) — lets
        # stop() interrupt all of them, and get_status() report per-device
        # progress instead of one shared string once multiple devices are
        # navigating concurrently.
        self._current_devices: dict[str, Any] = {}
        # Per-device status text (keyed by device name), populated by
        # _go_to_waypoint()/_navigate_to() instead of the old single
        # self._status_text, since concurrent devices would otherwise race
        # to overwrite the same string.
        self._device_status: dict[str, str] = {}
        # Current step's target, so a device added mid-operation via
        # on_device_joined() has somewhere to go.
        self._current_target: Optional[tuple[float, float]] = None
        # FleetContext, stashed here (the base class declares self._context
        # but operation_manager never actually populates it) so
        # on_device_joined() — which isn't passed a context — can still
        # dispatch navigation for a newly-recruited device.
        self._context: Optional[Any] = None
        # device_ids currently told to yield to a closer sibling — see
        # _collision_guard(). Checked by _go_to_waypoint_tracked() to pause
        # and later retry, rather than treating a guard-triggered stop as
        # a real failure.
        self._collision_paused: set[str] = set()
        # Per-device current waypoint (device_id -> (lat, lon)), set by
        # _navigate_one_waypoint() every time a device is sent toward a new
        # point. _collision_guard() uses this (falling back to
        # self._current_target) to judge yield priority — needed because
        # AREA_COVERAGE gives each device its own distinct path, so there's
        # no single shared target to compare distances against.
        self._device_target: dict[str, tuple[float, float]] = {}
        # Runs for the whole operation (not per-step) so a device added via
        # on_device_joined() mid-operation is covered too.
        self._guard_task: Optional[asyncio.Task] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self, context) -> None:
        self._context = context
        self._state = OperationState.RUNNING
        self._current_step = 0
        self._current_target = None
        self._device_status = {}
        self._collision_paused = set()
        self._device_target = {}
        self._guard_task = asyncio.create_task(self._collision_guard(context))

        steps = self._parse_steps()
        self._total_steps = len(steps)

        if not steps:
            self._status_text = "No steps configured"
            self._state = OperationState.COMPLETED
            return

        if not context.devices:
            self._status_text = "No devices assigned"
            self._state = OperationState.COMPLETED
            return

        no_lidar = [d.name for d in context.devices if not d.has_capability(DeviceCapability.LIDAR)]
        if no_lidar:
            await context.send_alert(
                "No obstacle detection",
                f"Navigating with no LiDAR configured — path is not checked for "
                f"obstacles: {', '.join(no_lidar)}",
                EventSeverity.WARNING,
            )

        logger.info(
            "%s: starting %d step(s) on %d device(s)",
            self.PLUGIN_ID, len(steps), len(context.devices)
        )

        try:
            for i, step in enumerate(steps):
                if self._stop_requested:
                    break

                self._current_step = i + 1
                self._status_text = (
                    f"Step {self._current_step}/{self._total_steps} — "
                    f"{step.step_type.value}"
                )
                logger.info("%s: %s", self.PLUGIN_ID, self._status_text)

                await self._execute_step(step, context)

        except asyncio.CancelledError:
            pass
        finally:
            self._current_target = None
            if self._guard_task is not None:
                self._guard_task.cancel()
                try:
                    await self._guard_task
                except asyncio.CancelledError:
                    pass
                self._guard_task = None
            self._state = OperationState.COMPLETED
            self._status_text = (
                "Stopped" if self._stop_requested else "Complete"
            )
            logger.info("%s: %s", self.PLUGIN_ID, self._status_text)

    async def stop(self) -> None:
        self._stop_requested = True
        self._state = OperationState.STOPPING
        # _navigate_to() (our cmd_vel fallback controller) checks
        # _stop_requested itself every tick. But device.move_to() — used
        # preferentially when a device implements cmd_move_to — can block
        # for the whole navigation (e.g. turtlebot3's proportional
        # controller), checking only its own internal stop flag. Explicitly
        # call device.stop() on every device currently mid-navigation to
        # interrupt them; must complete within 3s same as this method, and
        # stop() is a normal fast command, not a blocking loop, so running
        # them concurrently is safe.
        if self._current_devices:
            devices = list(self._current_devices.values())
            results = await asyncio.gather(
                *(d.stop() for d in devices), return_exceptions=True
            )
            for device, result in zip(devices, results):
                if isinstance(result, Exception):
                    logger.warning(
                        "%s: device.stop() failed for %s: %s",
                        self.PLUGIN_ID, device.name, result
                    )

    def get_status(self) -> OperationStatus:
        status_text = (
            "; ".join(f"{name}: {text}" for name, text in self._device_status.items())
            if self._device_status else self._status_text
        )
        return OperationStatus(
            state=self._state,
            status_text=status_text,
            progress_percent=(
                100.0 * self._current_step / self._total_steps
                if self._total_steps > 0 else None
            ),
            devices_active=list(self._current_devices.keys()),
            data={"devices": dict(self._device_status)},
        )

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution(
            display_name=self.OPERATION_NAME,
            description=self.OPERATION_DESCRIPTION,
            icon="navigation",
            config_schema={
                "step_type": {
                    "type": "select",
                    "label": "Step Type",
                    "required": True,
                    "options": [
                        {"label": "Move to Marker",   "value": StepType.MOVE_TO_MARKER},
                        {"label": "Move to Zone",     "value": StepType.MOVE_TO_ZONE},
                        {"label": "Area Coverage",    "value": StepType.AREA_COVERAGE},
                        {"label": "Perimeter Patrol", "value": StepType.PERIMETER_PATROL},
                    ],
                },
                "target_id": {
                    "type": "string",
                    "label": "Marker or Zone ID",
                    "required": True,
                    "placeholder": "From the map panel",
                },
                "speed_ms": {
                    "type": "number",
                    "label": "Speed (m/s)",
                    "required": False,
                    "default": 1.0,
                    "min": 0.1,
                    "max": 10.0,
                },
                "coverage_spacing_m": {
                    "type": "number",
                    "label": "Coverage Spacing (m)",
                    "required": False,
                    "default": 5.0,
                    "description": "Distance between sweep lanes — Area Coverage only",
                },
                "coverage_angle_deg": {
                    "type": "number",
                    "label": "Sweep Angle (°)",
                    "required": False,
                    "default": 0.0,
                    "min": 0,
                    "max": 359,
                    "description": "Sweep line direction, 0=east 90=north — Area Coverage only",
                },
                "patrol_laps": {
                    "type": "number",
                    "label": "Patrol Laps",
                    "required": False,
                    "default": 1,
                    "description": "Number of boundary loops — Perimeter Patrol only",
                },
            },
        )

    async def on_device_joined(self, device) -> None:
        """
        Called when the operator manually recruits a device into this running
        operation (operation_manager.recruit_device_into_operation() — there's
        no automatic join; a newly-connected device does nothing until the
        operator explicitly adds it). If a MOVE_TO_MARKER/MOVE_TO_ZONE target
        is currently active, send the new device there too, concurrently with
        whatever's already in flight — fire-and-forget, since nothing awaits
        this handler.
        """
        logger.info("%s: device joined — %s", self.PLUGIN_ID, device.name)
        if self._stop_requested or self._current_target is None or self._context is None:
            return
        lat, lon = self._current_target
        asyncio.create_task(self._go_to_waypoint_tracked(device, lat, lon, self._context))

    async def on_device_left(self, device) -> None:
        logger.warning("%s: device lost — %s", self.PLUGIN_ID, device.name)
        self._current_devices.pop(device.id, None)
        self._device_status.pop(device.name, None)
        if not self._current_devices:
            await self.stop()

    # ── Step dispatch ──────────────────────────────────────────────────────────

    async def _execute_step(self, step: NavigationStep, context) -> None:
        """
        Dispatch one step across every currently-assigned device.
        MOVE_TO_MARKER/MOVE_TO_ZONE resolve a single shared target once, then
        run all devices toward it concurrently (see _run_on_devices) — every
        matched robot starts at the same time. AREA_COVERAGE resolves one
        zone, splits it into a per-device path (see _execute_area_coverage),
        and runs every device on its own path concurrently. PERIMETER_PATROL
        remains an unimplemented per-device stub.
        """
        if step.step_type in (StepType.MOVE_TO_MARKER, StepType.MOVE_TO_ZONE):
            target = self._resolve_target(step, context)
            if target is None:
                return
            self._current_target = target
            await self._run_on_devices(list(context.devices), target, context)
        elif step.step_type == StepType.AREA_COVERAGE:
            await self._execute_area_coverage(step, context)
        elif step.step_type == StepType.PERIMETER_PATROL:
            for device in context.devices:
                await self._execute_perimeter_patrol(step, device, context)

    def _resolve_target(
        self, step: NavigationStep, context
    ) -> Optional[tuple[float, float]]:
        """Look up a MOVE_TO_MARKER/MOVE_TO_ZONE step's target once, shared
        across every device — avoids re-resolving the same marker/zone
        per-device now that they navigate concurrently."""
        if step.step_type == StepType.MOVE_TO_MARKER:
            marker = context.marker_manager.get_marker(step.marker_id) if step.marker_id else None
            if not marker:
                self._status_text = f"Marker not found: {step.marker_id}"
                logger.error("%s: %s", self.PLUGIN_ID, self._status_text)
                return None
            logger.info(
                "%s: MOVE_TO_MARKER — %s (%.5f, %.5f)",
                self.PLUGIN_ID, marker.name, marker.lat, marker.lon
            )
            return marker.lat, marker.lon

        if step.step_type == StepType.MOVE_TO_ZONE:
            zone = context.zone_manager.get_zone(step.zone_id) if step.zone_id else None
            if not zone:
                self._status_text = f"Zone not found: {step.zone_id}"
                logger.error("%s: %s", self.PLUGIN_ID, self._status_text)
                return None

            if zone.center is not None and zone.radius_m is not None:
                lat, lon = zone.center.lat, zone.center.lon
            elif zone.points:
                lat = sum(p.lat for p in zone.points) / len(zone.points)
                lon = sum(p.lon for p in zone.points) / len(zone.points)
            else:
                self._status_text = f"Zone has no geometry: {zone.name}"
                logger.error("%s: %s", self.PLUGIN_ID, self._status_text)
                return None

            logger.info(
                "%s: MOVE_TO_ZONE — %s centroid (%.5f, %.5f)",
                self.PLUGIN_ID, zone.name, lat, lon
            )
            return lat, lon

        return None

    async def _run_on_devices(
        self, devices: list, target: tuple[float, float], context
    ) -> None:
        """Send every device to the same target at the same time."""
        lat, lon = target
        await asyncio.gather(
            *(self._go_to_waypoint_tracked(device, lat, lon, context) for device in devices),
            return_exceptions=True,
        )

    async def _navigate_one_waypoint(
        self, device, target_lat: float, target_lon: float, context
    ) -> bool:
        """
        Drive to a single waypoint, honoring _collision_guard()'s pause/
        retry: if the guard interrupts this device (too close to a
        sibling), _go_to_waypoint() returns False same as any other failure
        — the difference is only visible via self._collision_paused, which
        the guard sets and clears. So: wait here while paused, then retry
        from wherever the device now is once clear, rather than treating a
        guard-triggered stop as a real failure. A genuine failure (no-go
        zone, timeout, real move_to() failure) returns False immediately.

        Records self._device_target so _collision_guard() can judge yield
        priority against THIS device's current waypoint — needed because
        AREA_COVERAGE has no single shared target (see _run_coverage_path).

        Registration in _current_devices (so stop() can interrupt) is the
        caller's job, not this function's — _go_to_waypoint_tracked()
        registers for one waypoint, _run_coverage_path() registers once for
        a whole multi-waypoint path.
        """
        self._device_target[device.id] = (target_lat, target_lon)
        while not self._stop_requested:
            while device.id in self._collision_paused and not self._stop_requested:
                self._device_status[device.name] = "Yielding to nearby robot"
                await asyncio.sleep(SEPARATION_CHECK_PERIOD_S)
            if self._stop_requested:
                return False

            result = await self._go_to_waypoint(device, target_lat, target_lon, context)
            if result:
                return True
            if device.id in self._collision_paused:
                continue
            return False
        return False

    async def _go_to_waypoint_tracked(
        self, device, target_lat: float, target_lon: float, context
    ) -> bool:
        """
        Wraps _navigate_one_waypoint() with the bookkeeping concurrent
        multi-device navigation needs: registers the device in
        _current_devices so stop() (and _collision_guard()) can interrupt
        it, and leaves its final status in _device_status for get_status()
        to report. Used both for the initial fleet-wide dispatch
        (_run_on_devices) and for a device joining mid-operation
        (on_device_joined).
        """
        self._current_devices[device.id] = device
        try:
            result = await self._navigate_one_waypoint(device, target_lat, target_lon, context)
            if result:
                self._device_status[device.name] = "Arrived"
            return result
        except asyncio.CancelledError:
            self._device_status[device.name] = "Stopped"
            raise
        finally:
            self._current_devices.pop(device.id, None)
            self._collision_paused.discard(device.id)
            self._device_target.pop(device.id, None)

    async def _collision_guard(self, context) -> None:
        """
        Runs for the whole operation (started in start(), not per-step) —
        checks pairwise distance between every currently-navigating device
        every SEPARATION_CHECK_PERIOD_S. If two are closer than
        MIN_SEPARATION_M, whichever is farther from ITS OWN current
        waypoint yields (tie-broken by device id for a stable, deterministic
        choice): flagged in _collision_paused and told to stop — the same
        device.stop() interruption already used for the operator Stop
        button, which works for both the move_to() path (turtlebot3) and
        the cmd_vel fallback (_navigate_to()), since neither controller
        needs to know this is happening. The other device keeps going.

        "Its own current waypoint" is self._device_target[device.id] —
        populated per-device by _navigate_one_waypoint() — falling back to
        self._current_target for safety. Per-device tracking (rather than
        one shared target) is what makes this apply during AREA_COVERAGE
        too, where every device is sweeping its own distinct path at once.

        For MOVE_TO_MARKER/MOVE_TO_ZONE specifically, this also handles
        multiple devices converging on the same point without a separate
        "spread the destination" step: once the leading device actually
        arrives, it's removed from _current_devices, the guard stops seeing
        a conflict, and whoever was yielding proceeds — so they arrive one
        at a time rather than contesting the same point simultaneously.
        """
        while not self._stop_requested:
            if len(self._current_devices) < 2:
                # Fewer than 2 devices means no possible conflict — clear any
                # pause left over from before a sibling arrived and was
                # removed from _current_devices, or a device that was
                # yielding could be stuck paused forever with nothing left
                # to yield to.
                self._collision_paused.clear()
                await asyncio.sleep(SEPARATION_CHECK_PERIOD_S)
                continue

            devices = list(self._current_devices.values())
            fixes: dict[str, tuple[Any, float, float]] = {}
            for d in devices:
                gps = await d.get_gps_data()
                if gps:
                    fixes[d.id] = (d, gps.lat, gps.lon)

            close_now: set[str] = set()
            ids = list(fixes.keys())
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    d1, lat1, lon1 = fixes[ids[i]]
                    d2, lat2, lon2 = fixes[ids[j]]
                    if _haversine_m(lat1, lon1, lat2, lon2) >= MIN_SEPARATION_M:
                        continue

                    close_now.add(d1.id)
                    close_now.add(d2.id)

                    target1 = self._device_target.get(d1.id, self._current_target)
                    target2 = self._device_target.get(d2.id, self._current_target)
                    if target1 is None or target2 is None:
                        # No known waypoint for one — fall back to a stable
                        # arbitrary tie-break rather than skip the pair.
                        loser = d1 if d1.id > d2.id else d2
                    else:
                        dist1 = _haversine_m(lat1, lon1, *target1)
                        dist2 = _haversine_m(lat2, lon2, *target2)
                        loser = d1 if (dist1, d1.id) > (dist2, d2.id) else d2

                    if loser.id not in self._collision_paused:
                        self._collision_paused.add(loser.id)
                        logger.warning(
                            "%s: %s yielding — within %.1fm of another robot",
                            self.PLUGIN_ID, loser.name, MIN_SEPARATION_M
                        )
                        await context.send_alert(
                            "Robots too close",
                            f"{loser.name} is yielding to a nearby robot",
                            EventSeverity.WARNING,
                        )
                        await loser.stop()

            # Clear anyone no longer in violation of any pair.
            for device_id in list(self._collision_paused):
                if device_id not in close_now:
                    self._collision_paused.discard(device_id)

            await asyncio.sleep(SEPARATION_CHECK_PERIOD_S)

    async def _go_to_waypoint(
        self, device, target_lat: float, target_lon: float, context
    ) -> bool:
        """
        Prefer the device's own cmd_move_to() (via device.move_to()) when
        implemented — e.g. turtlebot3, which uses real heading from /odom and
        gets DeviceProxy's dispatch for free. Falls back to _navigate_to()
        (generic cmd_vel + GPS course-over-ground heading estimate) only for
        devices that don't implement cmd_move_to, e.g. ue-sim. Checking the
        target against no-go zones happens once here, before either path —
        neither device.move_to() nor _navigate_to() does this on its own
        (device.move_to()'s docstring in zone_manager.py claims it does; the
        actual implementation doesn't).
        """
        no_go = context.zone_manager.is_in_no_go_zone(target_lat, target_lon)
        if no_go.inside:
            msg = f"Target is inside no-go zone: {no_go.zone_name}"
            self._device_status[device.name] = msg
            logger.warning("%s: %s", self.PLUGIN_ID, msg)
            await context.send_alert("Navigation blocked", msg, EventSeverity.WARNING)
            return False

        result = await device.move_to(target_lat, target_lon)
        if "not implemented" not in result.message.lower():
            # Device has a real cmd_move_to — trust its result rather than
            # driving ourselves.
            self._device_status[device.name] = result.message if not result.success else "Complete"
            if not result.success:
                logger.warning(
                    "%s: move_to failed for %s: %s", self.PLUGIN_ID, device.name, result.message
                )
            return result.success

        return await self._navigate_to(device, target_lat, target_lon, context)

    async def _navigate_to(
        self, device, target_lat: float, target_lon: float, context
    ) -> bool:
        """
        Closed-loop go-to-waypoint controller. Drives via the same generic
        cmd_vel contract teleop uses — straight-line only. Heading is
        estimated from GPS course-over-ground (bearing between consecutive
        fixes while moving), since this predates any device plugin reporting
        real heading. Fallback path only — see _go_to_waypoint(). Returns
        True on arrival, False on timeout or missing GPS.
        """

        heading: Optional[float] = None
        heading_ref_pos: Optional[tuple[float, float]] = None
        elapsed = 0.0
        blocked_since: Optional[float] = None

        try:
            while not self._stop_requested and elapsed < WAYPOINT_TIMEOUT_S:
                gps = await device.get_gps_data()
                if not gps:
                    await asyncio.sleep(CONTROL_PERIOD_S)
                    elapsed += CONTROL_PERIOD_S
                    continue

                distance = _haversine_m(gps.lat, gps.lon, target_lat, target_lon)
                if distance <= ARRIVAL_TOLERANCE_M:
                    await device.send_command("cmd_vel", {"linear": 0.0, "angular": 0.0})
                    return True

                if (
                    heading_ref_pos is None
                    or _haversine_m(*heading_ref_pos, gps.lat, gps.lon) >= MIN_MOVE_FOR_HEADING_M
                ):
                    if heading_ref_pos is not None:
                        new_estimate = _bearing_deg(*heading_ref_pos, gps.lat, gps.lon)
                        # Each estimate is an average bearing over the last movement
                        # segment, which is noisy while continuously turning — smooth
                        # it so a single noisy sample can't flip the turn direction
                        # (most damaging right at the 180° antipodal ambiguity).
                        heading = (
                            new_estimate if heading is None
                            else (heading + 0.5 * _angle_diff_deg(new_estimate, heading)) % 360
                        )
                    heading_ref_pos = (gps.lat, gps.lon)

                bearing_to_target = _bearing_deg(gps.lat, gps.lon, target_lat, target_lon)

                if heading is None:
                    # No heading estimate yet — drive straight briefly to establish one.
                    linear, angular = PROBE_LINEAR, 0.0
                else:
                    heading_error = _angle_diff_deg(bearing_to_target, heading)
                    angular = max(-MAX_ANGULAR, min(MAX_ANGULAR, heading_error / 45.0))
                    # Keep crawling forward even when badly misaligned — never a hard
                    # stop-and-spin, since that would freeze the heading estimate above.
                    alignment = max(MIN_ALIGNMENT_FRACTION, 1.0 - abs(heading_error) / 180.0)
                    slowdown = min(1.0, distance / SLOWDOWN_RADIUS_M)
                    linear = DRIVE_LINEAR * alignment * slowdown

                result = await device.send_command(
                    "cmd_vel", {"linear": linear, "angular": angular}
                )

                if not result.success and result.data.get("reason") == "obstacle":
                    if blocked_since is None:
                        blocked_since = elapsed
                        logger.warning(
                            "%s: %s blocked by obstacle, %.1f m from target",
                            self.PLUGIN_ID, device.name, distance
                        )
                        await context.send_alert(
                            "Obstacle detected",
                            f"{device.name}: path blocked {distance:.1f} m from "
                            f"target — waiting for it to clear",
                            EventSeverity.WARNING,
                        )
                    self._device_status[device.name] = f"Blocked by obstacle — {distance:.1f} m to target"
                    if elapsed - blocked_since >= OBSTACLE_BLOCKED_TIMEOUT_S:
                        self._device_status[device.name] = "Obstacle did not clear — navigation aborted"
                        logger.warning("%s: %s: %s", self.PLUGIN_ID, device.name, self._device_status[device.name])
                        return False
                else:
                    blocked_since = None
                    self._device_status[device.name] = f"{distance:.1f} m to target"

                await asyncio.sleep(CONTROL_PERIOD_S)
                elapsed += CONTROL_PERIOD_S

            await device.send_command("cmd_vel", {"linear": 0.0, "angular": 0.0})
            if elapsed >= WAYPOINT_TIMEOUT_S:
                self._device_status[device.name] = "Navigation timed out"
                logger.warning("%s: %s: %s", self.PLUGIN_ID, device.name, self._device_status[device.name])
            return False
        except asyncio.CancelledError:
            await device.send_command("cmd_vel", {"linear": 0.0, "angular": 0.0})
            raise

    async def _execute_area_coverage(self, step: NavigationStep, context) -> None:
        """
        Partition the target zone into as many strips as there are currently
        assigned devices (captured once, here — a device added later via
        on_device_joined does not get folded into a re-split; see the
        AREA_COVERAGE paragraph in the module docstring), generate a
        boustrophedon sweep path per strip (_generate_coverage_paths), and
        run every device through its own path concurrently
        (_run_coverage_path). Each device returns to the GPS position it was
        at when this step started once its sweep is done.
        """
        zone = context.zone_manager.get_zone(step.zone_id) if step.zone_id else None
        if not zone:
            self._status_text = f"Zone not found: {step.zone_id}"
            logger.error("%s: %s", self.PLUGIN_ID, self._status_text)
            return

        devices = list(context.devices)
        if not devices:
            return

        try:
            paths = _generate_coverage_paths(
                zone, len(devices), step.coverage_spacing_m, step.coverage_angle_deg
            )
        except ValueError as e:
            self._status_text = f"Coverage planning failed: {e}"
            logger.error("%s: %s", self.PLUGIN_ID, self._status_text)
            await context.send_alert("Coverage planning failed", str(e), EventSeverity.WARNING)
            return

        logger.info(
            "%s: AREA_COVERAGE — zone=%s spacing=%.1fm angle=%.0f° across %d device(s)",
            self.PLUGIN_ID, zone.name, step.coverage_spacing_m, step.coverage_angle_deg, len(devices)
        )

        start_positions: dict[str, Optional[tuple[float, float]]] = {}
        for device in devices:
            gps = await device.get_gps_data()
            start_positions[device.id] = (gps.lat, gps.lon) if gps else None

        await asyncio.gather(
            *(
                self._run_coverage_path(device, paths[i], start_positions[device.id], context)
                for i, device in enumerate(devices)
            ),
            return_exceptions=True,
        )

    async def _run_coverage_path(
        self,
        device,
        waypoints: list[tuple[float, float]],
        start_position: Optional[tuple[float, float]],
        context,
    ) -> bool:
        """
        Drive one device through its assigned AREA_COVERAGE sweep path, then
        back to start_position (its GPS fix captured when the step began).
        Registers/deregisters in _current_devices for the whole path (not
        per-waypoint) so stop() and _collision_guard() treat a device
        mid-sweep the same as one mid-single-waypoint navigation.
        """
        self._current_devices[device.id] = device
        try:
            if not waypoints:
                self._device_status[device.name] = "No coverage area assigned"

            for i, (lat, lon) in enumerate(waypoints):
                if self._stop_requested:
                    self._device_status[device.name] = "Stopped"
                    return False
                self._device_status[device.name] = f"Sweeping — waypoint {i + 1}/{len(waypoints)}"
                if not await self._navigate_one_waypoint(device, lat, lon, context):
                    self._device_status[device.name] = f"Coverage failed at waypoint {i + 1}/{len(waypoints)}"
                    return False

            if self._stop_requested:
                self._device_status[device.name] = "Stopped"
                return False

            if start_position is None:
                self._device_status[device.name] = "Complete — no start position to return to"
                return True

            self._device_status[device.name] = "Returning to start"
            ok = await self._navigate_one_waypoint(device, start_position[0], start_position[1], context)
            self._device_status[device.name] = (
                "Complete — returned to start" if ok else "Failed to return to start"
            )
            return ok
        except asyncio.CancelledError:
            self._device_status[device.name] = "Stopped"
            raise
        finally:
            self._current_devices.pop(device.id, None)
            self._collision_paused.discard(device.id)
            self._device_target.pop(device.id, None)

    async def _execute_perimeter_patrol(self, step: NavigationStep, device, context) -> None:
        """
        Follow the boundary of a zone for a set number of laps.

        TODO:
        - Look up zone polygon via context.zone_manager
        - Extract ordered boundary vertices
        - For each lap: send device.move_to() for each vertex in sequence
        - Check self._stop_requested between waypoints
        """
        logger.info(
            "%s: PERIMETER_PATROL — zone=%s laps=%d speed=%.1f m/s",
            self.PLUGIN_ID, step.zone_id, step.patrol_laps, step.speed_ms
        )
        # TODO: implement
        await asyncio.sleep(0)

    # ── Config parsing ─────────────────────────────────────────────────────────

    def _parse_steps(self) -> list[NavigationStep]:
        """
        Build the step list from operator config.

        Currently reads a single step from self._config.
        TODO: extend to support a list of steps when the UI supports it.
        """
        cfg = self._config or {}
        raw_type = cfg.get("step_type")
        if not raw_type:
            return []

        try:
            step_type = StepType(raw_type)
        except ValueError:
            logger.error("%s: unknown step_type %r", self.PLUGIN_ID, raw_type)
            return []

        target_id = cfg.get("target_id", "")
        step = NavigationStep(
            step_type=step_type,
            speed_ms=float(cfg.get("speed_ms", 1.0)),
            coverage_spacing_m=float(cfg.get("coverage_spacing_m", 5.0)),
            coverage_angle_deg=float(cfg.get("coverage_angle_deg", 0.0)),
            patrol_laps=int(cfg.get("patrol_laps", 1)),
        )

        if step_type == StepType.MOVE_TO_MARKER:
            step.marker_id = target_id
        else:
            step.zone_id = target_id

        return [step]
