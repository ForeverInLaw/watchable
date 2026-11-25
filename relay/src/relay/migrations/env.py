"""Alembic environment.

The relay runs migrations on startup on its own connection (relay.database.migrate).
The alembic CLI, used to write new revisions, connects to DATABASE_URL instead:

    DATABASE_URL=sqlite+aiosqlite:///data/relay.db uv run alembic revision --autogenerate -m "..."
"""

import asyncio
import os

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from relay.tables import metadata


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_cli_migrations() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is None:
    asyncio.run(run_cli_migrations())
else:
    run_migrations(connection)
