"""SQLite engine and schema migrations (Alembic, in relay/migrations)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

MIGRATIONS = "relay:migrations"


def connect_database(url: str) -> AsyncEngine:
    """Engine for an aiosqlite URL; the database file and its directory are created on demand."""
    database = make_url(url).database
    if database:
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url)
    event.listen(engine.sync_engine, "connect", _use_wal)
    return engine


def _use_wal(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def migrate(engine: AsyncEngine) -> None:
    """Upgrades the database to the latest migration."""
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)


def _upgrade(connection: Connection) -> None:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    # env.py runs on this connection instead of opening its own.
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
