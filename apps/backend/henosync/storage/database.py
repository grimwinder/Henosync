import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".henosync"
DB_PATH = DB_DIR / "henosync.db"


async def init_db() -> None:
    """Create all tables if they don't exist."""
    DB_DIR.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                plugin_id   TEXT NOT NULL,
                config      TEXT NOT NULL DEFAULT '{}',
                home_lat    REAL DEFAULT 0.0,
                home_lon    REAL DEFAULT 0.0,
                home_alt    REAL DEFAULT 0.0,
                created_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS zones (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                zone_type   TEXT NOT NULL,
                shape       TEXT NOT NULL,
                points      TEXT NOT NULL DEFAULT '[]',
                center_lat  REAL,
                center_lon  REAL,
                radius_m    REAL,
                created_by  TEXT NOT NULL DEFAULT 'operator',
                active      INTEGER NOT NULL DEFAULT 1,
                color       TEXT NOT NULL DEFAULT '#4A9EFF'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS map_markers (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                marker_type  TEXT NOT NULL,
                lat          REAL NOT NULL,
                lon          REAL NOT NULL,
                color        TEXT NOT NULL DEFAULT '#4A9EFF'
            )
        """)
        await db.commit()
        logger.info(f"Database initialized at {DB_PATH}")