import json
import logging
import aiosqlite
from datetime import datetime, timezone
from typing import Optional
from ..models import Mission, MissionCreate, MissionUpdate, MissionStatus
from .database import DB_PATH, init_db

logger = logging.getLogger(__name__)


async def _ensure_missions_table() -> None:
    """Create missions table if it doesn't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                status      TEXT NOT NULL,
                steps       TEXT NOT NULL DEFAULT '[]',
                failsafe    TEXT NOT NULL DEFAULT '{}',
                metadata    TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        await db.commit()


class MissionStore:
    """
    Handles all mission persistence to SQLite.
    Missions are stored as JSON in the database.
    """

    async def initialize(self) -> None:
        """Initialize the mission store."""
        await _ensure_missions_table()
        logger.info("Mission store initialized")

    async def create(self, mission_create: MissionCreate) -> Mission:
        """Create and save a new mission."""
        now = datetime.now(timezone.utc).isoformat()
        mission = Mission(
            name=mission_create.name,
            steps=mission_create.steps,
            failsafe=mission_create.failsafe,
            metadata=mission_create.metadata
        )

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO missions
                (id, name, status, steps, failsafe, metadata,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mission.id,
                mission.name,
                mission.status.value,
                json.dumps([s.model_dump() for s in mission.steps]),
                json.dumps(mission.failsafe.model_dump()),
                json.dumps(mission.metadata),
                now,
                now
            ))
            await db.commit()

        logger.info(f"Created mission: {mission.name} ({mission.id})")
        return mission

    async def get(self, mission_id: str) -> Optional[Mission]:
        """Get a mission by id."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM missions WHERE id = ?",
                (mission_id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None
        return self._row_to_mission(row)

    async def get_all(self) -> list[Mission]:
        """Get all missions."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM missions ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()

        return [self._row_to_mission(row) for row in rows]

    async def update(
        self,
        mission_id: str,
        update: MissionUpdate
    ) -> Optional[Mission]:
        """Update a mission."""
        mission = await self.get(mission_id)
        if not mission:
            return None

        if update.name is not None:
            mission.name = update.name
        if update.steps is not None:
            mission.steps = update.steps
        if update.failsafe is not None:
            mission.failsafe = update.failsafe
        if update.metadata is not None:
            mission.metadata = update.metadata

        now = datetime.now(timezone.utc).isoformat()
        mission.updated_at = datetime.now(timezone.utc)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                UPDATE missions
                SET name=?, steps=?, failsafe=?, metadata=?, updated_at=?
                WHERE id=?
            """, (
                mission.name,
                json.dumps([s.model_dump() for s in mission.steps]),
                json.dumps(mission.failsafe.model_dump()),
                json.dumps(mission.metadata),
                now,
                mission_id
            ))
            await db.commit()

        return mission

    async def delete(self, mission_id: str) -> bool:
        """Delete a mission."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM missions WHERE id = ?",
                (mission_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_status(
        self,
        mission_id: str,
        status: MissionStatus
    ) -> None:
        """Update just the status of a mission."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE missions SET status=? WHERE id=?",
                (status.value, mission_id)
            )
            await db.commit()

    def _row_to_mission(self, row) -> Mission:
        """Convert a database row to a Mission object."""
        return Mission(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            steps=json.loads(row["steps"]),
            failsafe=json.loads(row["failsafe"]),
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )


# Global singleton
mission_store = MissionStore()