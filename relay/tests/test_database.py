"""The SQLite file holds notification and reply text, so only its owner may read it."""

import asyncio
import stat
from pathlib import Path

from relay.database import connect_database, migrate


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def open_database(path: Path) -> None:
    async def run() -> None:
        engine = connect_database(f"sqlite+aiosqlite:///{path}")
        await migrate(engine)
        await engine.dispose()

    asyncio.run(run())


def test_new_database_is_readable_by_its_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "data" / "relay.db"

    open_database(path)

    assert mode_of(path) == 0o600


def test_existing_database_is_made_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "relay.db"
    wal = tmp_path / "relay.db-wal"
    for file in (path, wal):
        file.touch(mode=0o644)
        file.chmod(0o644)

    connect_database(f"sqlite+aiosqlite:///{path}")

    assert (mode_of(path), mode_of(wal)) == (0o600, 0o600)
