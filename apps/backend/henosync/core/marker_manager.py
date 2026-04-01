import logging
import uuid
import aiosqlite
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from ..storage.database import DB_PATH, init_db

logger = logging.getLogger(__name__)


class MarkerType(str, Enum):
    HOME_POSITION = "home_position"
    WAYPOINT = "waypoint"
    REFERENCE = "reference"
    HAZARD = "hazard"
    CUSTOM = "custom"


class MapMarker(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    marker_type: MarkerType
    lat: float
    lon: float
    color: str = "#4A9EFF"


class MarkerManager:
    def __init__(self):
        self._markers: dict[str, MapMarker] = {}

    async def initialize(self) -> None:
        await init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM map_markers") as cur:
                rows = await cur.fetchall()
        for row in rows:
            marker = MapMarker(
                id=row["id"],
                name=row["name"],
                marker_type=MarkerType(row["marker_type"]),
                lat=row["lat"],
                lon=row["lon"],
                color=row["color"],
            )
            self._markers[marker.id] = marker
        logger.info(f"Marker manager loaded {len(self._markers)} markers")

    async def create_marker(
        self,
        name: str,
        marker_type: MarkerType,
        lat: float,
        lon: float,
        color: str = "#4A9EFF",
    ) -> MapMarker:
        marker = MapMarker(name=name, marker_type=marker_type, lat=lat, lon=lon, color=color)
        self._markers[marker.id] = marker
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO map_markers (id, name, marker_type, lat, lon, color) VALUES (?, ?, ?, ?, ?, ?)",
                (marker.id, marker.name, marker.marker_type.value, marker.lat, marker.lon, marker.color),
            )
            await db.commit()
        logger.info(f"Marker created: {name} ({marker_type})")
        return marker

    async def delete_marker(self, marker_id: str) -> bool:
        if marker_id not in self._markers:
            return False
        name = self._markers[marker_id].name
        del self._markers[marker_id]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM map_markers WHERE id = ?", (marker_id,))
            await db.commit()
        logger.info(f"Marker deleted: {name}")
        return True

    def get_all_markers(self) -> list[MapMarker]:
        return list(self._markers.values())


marker_manager = MarkerManager()