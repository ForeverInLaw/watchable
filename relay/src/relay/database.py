"""SQLite engine and schema migrations (Alembic, in relay/migrations)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

MIGRATIONS = "relay:migrations"


MEMORY_DATABASE = ":memory:"
# SQLite's own files next to the database while it is open in WAL mode.
SIDE_FILE_SUFFIXES = ("-wal", "-shm")


def connect_database(url: str) -> AsyncEngine:
    """Engine for an aiosqlite URL; the database file and its directory are created on demand."""
    database = make_url(url).database
    if database and database != MEMORY_DATABASE:
        _make_owner_only(Path(database))
    engine = create_async_engine(url)
    event.listen(engine.sync_engine, "connect", _use_wal)
    return engine


def _make_owner_only(path: Path) -> None:
    """Creates the database file readable by its owner only, since it holds notification and
    reply text (TZ §10), and narrows a file an older relay created. SQLite gives the WAL and
    shared-memory files it creates later the mode of the database file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    for file in (path, *(path.with_name(path.name + suffix) for suffix in SIDE_FILE_SUFFIXES)):
        if file.exists():
            file.chmod(0o600)


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
