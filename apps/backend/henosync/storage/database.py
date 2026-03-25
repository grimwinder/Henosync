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
        await db.commit()
        logger.info(f"Database initialized at {DB_PATH}")