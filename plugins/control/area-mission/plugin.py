"""
Area Mission — abstract mission description.

Operator draws/selects a zone (existing Zones page) and picks a mission
style: "scan" (boustrophedon coverage sweep) or "patrol" (loop the zone
boundary). This plugin generates the waypoint list itself and drives it
through DeviceProxy.move_to() one waypoint at a time — no new navigation
primitive, just waypoint generation on top of the existing closed-loop
per-device move_to() controller.

GPS zones only (map_mode == "gps") — VICON is out of scope for this plugin.

Coverage scope (v1): rectangles / simple convex zones. Waypoints are found
by point-sampling each sweep row against the target zone via
zone_manager.is_point_in_zone() and skipping any point inside a NO_GO zone
via zone_manager.is_in_no_go_zone() — there is no dedicated geometric
clipping step, so a highly concave zone may produce a broken sweep.

Safety: each waypoint move is wrapped in asyncio.wait_for(timeout). A
stale/lost GPS fix (or any other move_to stall) times out and aborts the
whole operation rather than continuing blind — mirrors auto-navigate's
existing per-move timeout pattern. Cancelling the awaited move_to on
timeout also triggers the device plugin's own try/finally zero-velocity
publish (confirmed present in jackal and turtlebot3's cmd_move_to).
"""

import asyncio
import logging
import math

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

EARTH_RADIUS_M = 6_371_000.0


def _to_local(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Equirectangular projection to metres, relative to a reference point."""
    dlat = math.radians(lat - ref_lat)
    dlon = math.radians(lon - ref_lon)
    x = dlon * EARTH_RADIUS_M * math.cos(math.radians(ref_lat))
    y = dlat * EARTH_RADIUS_M
    return x, y


def _to_gps(x: float, y: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Inverse of _to_local."""
    dlat = y / EARTH_RADIUS_M
    dlon = x / (EARTH_RADIUS_M * math.cos(math.radians(ref_lat)))
    return ref_lat + math.degrees(dlat), ref_lon + math.degrees(dlon)


def _zone_bounds_local(zone) -> tuple[float, float, float, float, float, float]:
    """Returns (ref_lat, ref_lon, min_x, max_x, min_y, max_y) for a zone's bounding box."""
    if zone.shape == "circle":
        ref_lat, ref_lon = zone.center.lat, zone.center.lon
        r = zone.radius_m
        return ref_lat, ref_lon, -r, r, -r, r

    lats = [p.lat for p in zone.points]
    lons = [p.lon for p in zone.points]
    ref_lat = sum(lats) / len(lats)
    ref_lon = sum(lons) / len(lons)
    xs, ys = [], []
    for p in zone.points:
        x, y = _to_local(p.lat, p.lon, ref_lat, ref_lon)
        xs.append(x)
        ys.append(y)
    return ref_lat, ref_lon, min(xs), max(xs), min(ys), max(ys)


def _generate_scan_waypoints(
    zone, zone_manager, spacing_m: float
) -> list[tuple[float, float]]:
    """
    Boustrophedon (lawnmower) sweep over a zone's bounding box.

    Point-sampled: for each row, scans along x at a fine step and keeps the
    first/last point that is inside the target zone and outside any NO_GO
    zone. Handles rectangles and simple convex shapes well; a concave zone
    or one broken into disjoint pieces by a NO_GO zone will only get the
    single entry/exit pair per row (no multi-segment splitting).
    """
    ref_lat, ref_lon, min_x, max_x, min_y, max_y = _zone_bounds_local(zone)
    fine_step = max(0.5, spacing_m / 5.0)

    waypoints: list[tuple[float, float]] = []
    row_idx = 0
    y = min_y
    while y <= max_y + 1e-9:
        row_xs: list[float] = []
        x = min_x
        while x <= max_x + 1e-9:
            lat, lon = _to_gps(x, y, ref_lat, ref_lon)
            if zone_manager.is_point_in_zone(lat, lon, zone) and not zone_manager.is_in_no_go_zone(lat, lon).inside:
                row_xs.append(x)
            x += fine_step

        if row_xs:
            start_x, end_x = row_xs[0], row_xs[-1]
            if row_idx % 2 == 1:
                start_x, end_x = end_x, start_x
            waypoints.append(_to_gps(start_x, y, ref_lat, ref_lon))
            waypoints.append(_to_gps(end_x, y, ref_lat, ref_lon))
            row_idx += 1

        y += spacing_m

    return waypoints


def _generate_patrol_waypoints(zone) -> list[tuple[float, float]]:
    """Zone boundary as a waypoint loop. Circle zones get a sampled ring."""
    if zone.shape == "circle":
        ref_lat, ref_lon = zone.center.lat, zone.center.lon
        r = zone.radius_m
        count = max(8, int((2 * math.pi * r) / 3.0))
        points = []
        for i in range(count):
            angle = 2 * math.pi * i / count
            x, y = r * math.cos(angle), r * math.sin(angle)
            points.append(_to_gps(x, y, ref_lat, ref_lon))
        return points

    return [(p.lat, p.lon) for p in zone.points]


class AreaMissionPlugin(ControlPlugin):
    PLUGIN_ID = "area-mission"
    PLUGIN_NAME = "Area Mission"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    OPERATION_NAME = "Area Mission"
    OPERATION_DESCRIPTION = "Draw a zone, pick scan or patrol — the robot generates and drives its own waypoints."

    REQUIRED_CAPABILITIES: list[CapabilityRequirement] = [
        CapabilityRequirement(capability=DeviceCapability.MOVE_2D, required=True),
    ]

    SUPPORTED_CATEGORIES: list[DeviceCategory] = [
        DeviceCategory.AGV,
        DeviceCategory.DRONE,
        DeviceCategory.LEGGED,
        DeviceCategory.TRACKED,
        DeviceCategory.VTOL,
    ]

    PRIORITY: int = 5

    def __init__(self) -> None:
        super().__init__()
        self._state: OperationState = OperationState.IDLE
        self._status_text: str = ""
        self._progress_percent: float | None = None
        self._active_device = None
        self._waypoint_index: int = 0
        self._total_waypoints: int = 0
        self._infinite: bool = False

    async def start(self, context) -> None:
        self._state = OperationState.RUNNING
        mission_type = self._config.get("mission_type", "scan")

        # ── Resolve device ─────────────────────────────────────
        target_node_id = self._config.get("node_id", "")
        if target_node_id:
            device = next((d for d in context.devices if d.id == target_node_id), None)
            if device is None:
                self._fail(f"Robot {target_node_id!r} not available")
                return
        else:
            if not context.devices:
                self._fail("No compatible device available")
                return
            device = context.devices[0]

        # ── Resolve zone ───────────────────────────────────────
        zone_id = self._config.get("zone_id", "")
        zone = context.zone_manager.get_zone(zone_id)
        if zone is None:
            await self._fail_alert(context, "Area Mission failed", f"Zone not found: {zone_id!r}")
            return
        if zone.map_mode != "gps":
            await self._fail_alert(
                context, "Area Mission failed",
                f"Zone {zone.name!r} is a VICON zone — Area Mission only supports GPS zones.",
            )
            return

        spacing_m = float(self._config.get("sweep_spacing_m", 3.0))
        arrival_radius_m = float(self._config.get("arrival_radius_m", 0.5))
        waypoint_timeout_s = float(self._config.get("waypoint_timeout_s", 60.0))
        patrol_laps = int(self._config.get("patrol_laps", 1) or 0)
        max_speed = self._config.get("max_speed") or None
        if max_speed is not None:
            max_speed = float(max_speed)

        # ── Generate waypoints ───────────────────────────────────
        if mission_type == "scan":
            base_waypoints = _generate_scan_waypoints(zone, context.zone_manager, spacing_m)
            infinite = False
        else:
            base_waypoints = [
                (lat, lon) for lat, lon in _generate_patrol_waypoints(zone)
                if not context.zone_manager.is_in_no_go_zone(lat, lon).inside
            ]
            infinite = patrol_laps <= 0

        if len(base_waypoints) < 2:
            await self._fail_alert(
                context, "Area Mission failed",
                f"Could not generate a usable path for zone {zone.name!r} — it may be too small "
                "or fully blocked by a no-go zone.",
            )
            return

        waypoints = base_waypoints if infinite else base_waypoints * max(1, patrol_laps)
        self._total_waypoints = len(waypoints)
        self._waypoint_index = 0
        self._infinite = infinite
        self._active_device = device

        logger.info(
            "AreaMission: %s on %s → %s (%d waypoints, spacing=%.1fm)",
            mission_type, device.name, zone.name, self._total_waypoints, spacing_m,
        )

        # ── Drive waypoints ───────────────────────────────────────
        if infinite:
            idx = 0
            while not self._stop_requested:
                lat, lon = base_waypoints[idx % len(base_waypoints)]
                if not await self._goto(
                    context, device, lat, lon, arrival_radius_m, max_speed,
                    waypoint_timeout_s, idx, infinite=True,
                ):
                    return
                idx += 1
                self._waypoint_index = idx
        else:
            for i, (lat, lon) in enumerate(waypoints):
                if self._stop_requested:
                    break
                if not await self._goto(
                    context, device, lat, lon, arrival_radius_m, max_speed,
                    waypoint_timeout_s, i,
                ):
                    return
                self._waypoint_index = i + 1

        if self._stop_requested:
            self._status_text = "Stopped"
        else:
            self._status_text = f"{mission_type.capitalize()} complete — {self._total_waypoints} waypoints"
            self._progress_percent = 100.0
        self._state = OperationState.COMPLETED

    async def _goto(
        self, context, device, lat: float, lon: float,
        arrival_radius_m: float, max_speed, timeout_s: float,
        idx: int, infinite: bool = False,
    ) -> bool:
        """Drive to one waypoint. Returns False (and sets FAILED state) on timeout/failure."""
        label = f"waypoint {idx + 1}" if infinite else f"waypoint {idx + 1}/{self._total_waypoints}"
        self._status_text = f"Moving to {label}"
        try:
            result = await asyncio.wait_for(
                device.move_to(lat, lon, 0.0, arrival_radius_m=arrival_radius_m, max_speed=max_speed),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            self._status_text = f"Timed out at {label}"
            self._state = OperationState.FAILED
            await context.send_alert(
                "Area Mission timeout",
                f"{device.name} did not reach {label} within {timeout_s:.0f}s — aborting "
                "(check GPS fix — a stale/lost position is the most common cause).",
                EventSeverity.WARNING,
            )
            return False

        if not result.success:
            self._status_text = f"Move failed at {label}: {result.message}"
            self._state = OperationState.FAILED
            await context.send_alert("Area Mission failed", result.message, EventSeverity.WARNING)
            return False

        return True

    def _fail(self, message: str) -> None:
        self._status_text = message
        self._state = OperationState.FAILED

    async def _fail_alert(self, context, title: str, message: str) -> None:
        self._fail(message)
        await context.send_alert(title, message, EventSeverity.WARNING)

    async def stop(self) -> None:
        self._stop_requested = True
        self._state = OperationState.STOPPING
        dev = self._active_device
        if dev:
            try:
                await dev.stop()
            except Exception:
                pass

    def get_status(self) -> OperationStatus:
        progress = self._progress_percent
        if progress is None and self._total_waypoints and not self._infinite:
            progress = 100.0 * self._waypoint_index / self._total_waypoints
        return OperationStatus(
            state=self._state,
            status_text=self._status_text,
            progress_percent=progress,
        )

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution(
            display_name="Area Mission",
            description="Draw a zone, pick scan or patrol — the robot generates and drives its own waypoints.",
            icon="map",
            config_schema={
                "mission_type": {
                    "type": "select",
                    "label": "Mission Style",
                    "required": True,
                    "default": "scan",
                    "options": [
                        {"label": "Scan (coverage sweep)", "value": "scan"},
                        {"label": "Patrol (loop boundary)", "value": "patrol"},
                    ],
                },
                "zone_id": {
                    "type": "zone_select",
                    "label": "Zone",
                    "required": True,
                    "description": "GPS zone to scan or patrol. Draw/edit zones on the Zones page.",
                },
                "node_id": {
                    "type": "device_select",
                    "label": "Robot",
                    "required": False,
                    "description": "Which robot to send. Leave blank to use the first available.",
                },
                "sweep_spacing_m": {
                    "type": "number",
                    "label": "Sweep Spacing (m)",
                    "required": False,
                    "default": 3.0,
                    "min": 0.5,
                    "max": 50.0,
                    "show_when": {"field": "mission_type", "value": "scan"},
                    "description": "Distance between coverage sweep rows — set close to sensor footprint width.",
                },
                "patrol_laps": {
                    "type": "number",
                    "label": "Laps",
                    "required": False,
                    "default": 1,
                    "min": 0,
                    "max": 100,
                    "show_when": {"field": "mission_type", "value": "patrol"},
                    "description": "Times around the boundary. 0 = loop until stopped.",
                },
                "arrival_radius_m": {
                    "type": "number",
                    "label": "Arrival Radius (m)",
                    "required": False,
                    "default": 0.5,
                    "min": 0.05,
                    "max": 20.0,
                    "description": "Distance from each waypoint considered 'reached'.",
                },
                "waypoint_timeout_s": {
                    "type": "number",
                    "label": "Per-Waypoint Timeout (s)",
                    "required": False,
                    "default": 60,
                    "min": 10,
                    "max": 600,
                    "description": "Abort the whole mission if a single waypoint isn't reached in time "
                    "(e.g. lost GPS fix).",
                },
                "max_speed": {
                    "type": "number",
                    "label": "Max Speed (m/s)",
                    "required": False,
                    "min": 0.01,
                    "max": 2.0,
                    "placeholder": "Device max",
                    "description": "Cap the navigation speed. Leave blank for device maximum.",
                },
            },
        )

    async def on_device_left(self, device) -> None:
        logger.warning("AreaMission: device lost — %s", device.name)
        await self.stop()
