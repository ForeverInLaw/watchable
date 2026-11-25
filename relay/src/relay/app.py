"""HTTP API of the relay (docs/TZ.md §9.2): pairing, notification intake and the health check.

Run with `uvicorn --factory relay.app:app_from_env`; see the README.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException

from relay.api import ApiError, CurrentRelay, Relay, answer_error
from relay.apns import ApnsSender, ApnsSettings
from relay.clock import Clock, utc_now
from relay.database import connect_database, migrate
from relay.devices import PUSH_TOKEN_SCHEMA, DeviceRegistry
from relay.events import EVENT_SCHEMA
from relay.intake import NotificationIntake
from relay.pairing import (
    PAIR_COMPLETE_SCHEMA,
    PAIR_START_SCHEMA,
    PAIR_STARTS_PER_MINUTE,
    Pairing,
)
from relay.protocol import BodyParser
from relay.ratelimit import RateLimit
from relay.routes import events, pairing
from relay.settings import RelaySettings
from relay.store import EventStore

health = APIRouter()


@health.get("/healthz")
async def healthz(relay: CurrentRelay) -> dict[str, str]:
    async with relay.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}


def create_app(
    settings: RelaySettings, connect_apns: Callable[[], ApnsSender], clock: Clock = utc_now
) -> FastAPI:
    """The relay app; `connect_apns` runs at startup, inside the event loop aioapns needs."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = connect_database(settings.database_url)
        await migrate(engine)
        protocol_dir = settings.protocol_dir
        app.state.relay = Relay(
            engine=engine,
            devices=DeviceRegistry(engine, clock),
            pairing=Pairing(engine, clock, timedelta(seconds=settings.pairing_ttl_seconds)),
            pair_start_limit=RateLimit(PAIR_STARTS_PER_MINUTE, timedelta(minutes=1), clock),
            intake=NotificationIntake(
                EventStore(engine, timedelta(days=settings.retention_days)), connect_apns(), clock
            ),
            event_parser=BodyParser(protocol_dir, EVENT_SCHEMA),
            pair_start_parser=BodyParser(protocol_dir, PAIR_START_SCHEMA),
            pair_complete_parser=BodyParser(protocol_dir, PAIR_COMPLETE_SCHEMA),
            push_token_parser=BodyParser(protocol_dir, PUSH_TOKEN_SCHEMA),
        )
        yield
        await engine.dispose()

    app = FastAPI(title="Relay", lifespan=lifespan)
    for error_type in (ApiError, HTTPException, RequestValidationError, Exception):
        app.add_exception_handler(error_type, answer_error)
    for router in (health, pairing.router, events.router):
        app.include_router(router)
    return app


def app_from_env() -> FastAPI:
    """Uvicorn factory: settings from the environment, a real APNs connection."""
    return create_app(RelaySettings(), connect_apns=lambda: ApnsSender.connect(ApnsSettings()))
