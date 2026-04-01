import math
import json
import logging
import uuid
import aiosqlite
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum
from ..models import Position
from ..storage.database import DB_PATH, init_db

logger = logging.getLogger(__name__)


class ZoneType(str, Enum):
    PERIMETER = "perimeter"      # Operational boundary
    NO_GO = "no_go"             # Exclusion zone — enforced by core
    SAFE_RETURN = "safe_return"  # Home base zone
    COVERAGE = "coverage"        # Area to be covered
    ALERT = "alert"              # Alert on entry/exit
    CUSTOM = "custom"            # Plugin-defined zone type


class ZoneShape(str, Enum):
    POLYGON = "polygon"
    CIRCLE = "circle"


class GeoPoint(BaseModel):
    lat: float
    lon: float


class Zone(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    zone_type: ZoneType
    shape: ZoneShape = ZoneShape.POLYGON
    # For polygon zones
    points: list[GeoPoint] = []
    # For circle zones
    center: Optional[GeoPoint] = None
    radius_m: Optional[float] = None
    # Metadata
    created_by: str = "operator"  # "operator" or plugin_id
    active: bool = True
    color: str = "#F05252"        # Display color on map


class ZoneCheckResult(BaseModel):
    inside: bool
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: Optional[ZoneType] = None


class ZoneManager:
    """
    Manages geographic zones for the entire system.

    Responsibilities:
    - Create, update, delete zones
    - Check if positions are inside zones
    - Enforce no-go zones on movement commands
    - Notify when devices enter/exit zones

    No-go zone enforcement:
    The DeviceProxy.move_to() checks with ZoneManager before
    dispatching movement. If target is in a no-go zone,
    the command is blocked and a failed CommandResult returned.
    The control plugin's algorithm receives this failure and
    must decide how to respond (go around, alert operator etc.)
    """

    def __init__(self):
        self._zones: dict[str, Zone] = {}

    # ── Lifecycle ──────────────────────────────────────────────

    async def initialize(self) -> None:
        """Load persisted zones from database on startup."""
        await init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM zones WHERE active = 1") as cur:
                rows = await cur.fetchall()
        for row in rows:
            center = None
            if row["center_lat"] is not None and row["center_lon"] is not None:
                center = GeoPoint(lat=row["center_lat"], lon=row["center_lon"])
            points = [GeoPoint(**p) for p in json.loads(row["points"])]
            zone = Zone(
                id=row["id"],
                name=row["name"],
                zone_type=ZoneType(row["zone_type"]),
                shape=ZoneShape(row["shape"]),
                points=points,
                center=center,
                radius_m=row["radius_m"],
                created_by=row["created_by"],
                active=bool(row["active"]),
                color=row["color"],
            )
            self._zones[zone.id] = zone
        logger.info(f"Zone manager loaded {len(self._zones)} zones")

    # ── Zone CRUD ──────────────────────────────────────────────

    async def create_zone(
        self,
        name: str,
        zone_type: ZoneType,
        points: Optional[list[GeoPoint]] = None,
        center: Optional[GeoPoint] = None,
        radius_m: Optional[float] = None,
        created_by: str = "operator",
        color: str = "#4A9EFF"
    ) -> Zone:
        """Create a new zone and persist to database."""
        points = points or []
        shape = ZoneShape.CIRCLE if center and radius_m else ZoneShape.POLYGON
        zone = Zone(
            name=name,
            zone_type=zone_type,
            shape=shape,
            points=points,
            center=center,
            radius_m=radius_m,
            created_by=created_by,
            color=color
        )
        self._zones[zone.id] = zone
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO zones
                (id, name, zone_type, shape, points, center_lat, center_lon,
                 radius_m, created_by, active, color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                zone.id, zone.name, zone.zone_type.value, zone.shape.value,
                json.dumps([p.model_dump() for p in zone.points]),
                center.lat if center else None,
                center.lon if center else None,
                radius_m, created_by, 1, color
            ))
            await db.commit()
        logger.info(f"Zone created: {name} ({zone_type}) by {created_by}")
        return zone

    async def delete_zone(self, zone_id: str) -> bool:
        """Delete a zone and remove from database."""
        if zone_id not in self._zones:
            return False
        name = self._zones[zone_id].name
        del self._zones[zone_id]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
            await db.commit()
        logger.info(f"Zone deleted: {name}")
        return True

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Get a zone by ID."""
        return self._zones.get(zone_id)

    def get_all_zones(self) -> list[Zone]:
        """Get all zones."""
        return [z for z in self._zones.values() if z.active]

    def get_zones_by_type(self, zone_type: ZoneType) -> list[Zone]:
        """Get all active zones of a specific type."""
        return [
            z for z in self._zones.values()
            if z.active and z.zone_type == zone_type
        ]

    # ── Zone Checking ──────────────────────────────────────────

    def is_in_no_go_zone(
        self,
        lat: float,
        lon: float
    ) -> ZoneCheckResult:
        """
        Check if a position is inside any no-go zone.
        Called by DeviceProxy.move_to() before dispatching.
        """
        no_go_zones = self.get_zones_by_type(ZoneType.NO_GO)
        for zone in no_go_zones:
            if self._is_inside_zone(lat, lon, zone):
                return ZoneCheckResult(
                    inside=True,
                    zone_id=zone.id,
                    zone_name=zone.name,
                    zone_type=zone.zone_type
                )
        return ZoneCheckResult(inside=False)

    def check_position(
        self,
        lat: float,
        lon: float
    ) -> list[ZoneCheckResult]:
        """
        Check which zones a position is inside.
        Returns results for all matching zones.
        """
        results = []
        for zone in self._zones.values():
            if zone.active and self._is_inside_zone(lat, lon, zone):
                results.append(ZoneCheckResult(
                    inside=True,
                    zone_id=zone.id,
                    zone_name=zone.name,
                    zone_type=zone.zone_type
                ))
        return results

    # ── Geometry ───────────────────────────────────────────────

    def _is_inside_zone(
        self,
        lat: float,
        lon: float,
        zone: Zone
    ) -> bool:
        """Check if a point is inside a zone."""
        if zone.shape == ZoneShape.CIRCLE:
            return self._is_in_circle(lat, lon, zone)
        return self._is_in_polygon(lat, lon, zone)

    def _is_in_circle(
        self,
        lat: float,
        lon: float,
        zone: Zone
    ) -> bool:
        """Check if point is within circle zone radius."""
        if not zone.center or not zone.radius_m:
            return False
        dist = self._haversine(
            lat, lon,
            zone.center.lat, zone.center.lon
        )
        return dist <= zone.radius_m

    def _is_in_polygon(
        self,
        lat: float,
        lon: float,
        zone: Zone
    ) -> bool:
        """
        Ray casting algorithm for point-in-polygon.
        Works with GPS coordinates.
        """
        if len(zone.points) < 3:
            return False

        points = zone.points
        n = len(points)
        inside = False
        j = n - 1

        for i in range(n):
            xi, yi = points[i].lon, points[i].lat
            xj, yj = points[j].lon, points[j].lat

            if (
                (yi > lat) != (yj > lat) and
                lon < (xj - xi) * (lat - yi) / (yj - yi) + xi
            ):
                inside = not inside
            j = i

        return inside

    def _haversine(
        self,
        lat1: float, lon1: float,
        lat2: float, lon2: float
    ) -> float:
        """Calculate distance between two GPS points in metres."""
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)

        a = (
            math.sin(dphi / 2) ** 2 +
            math.cos(phi1) * math.cos(phi2) *
            math.sin(dlam / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Global singleton
zone_manager = ZoneManager()