"""HTTP API of the relay (docs/TZ.md §9.2): pairing, notifications, replies and the health check.

Run with `uvicorn --factory relay.app:app_from_env`; see the README.
"""

import logging
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
from relay.devices import PUSH_TOKEN_SCHEMA, WATCH_PUSH_TOKEN_SCHEMA, DeviceRegistry
from relay.events import EVENT_SCHEMA
from relay.fcm import FcmSender, FcmSettings
from relay.intake import NotificationIntake
from relay.pairing import (
    PAIR_COMPLETE_SCHEMA,
    PAIR_START_SCHEMA,
    PAIR_STARTS_PER_MINUTE,
    Pairing,
)
from relay.protocol import BodyParser
from relay.ratelimit import RateLimit
from relay.replies import (
    REPLIES_PER_MINUTE,
    REPLY_SCHEMA,
    RESULT_SCHEMA,
    ReplyDispatch,
    ReplyStore,
)
from relay.routes import events, pairing, replies
from relay.settings import RelaySettings
from relay.store import EventStore

health = APIRouter()


@health.get("/healthz")
async def healthz(relay: CurrentRelay) -> dict[str, str]:
    async with relay.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}


def create_app(
    settings: RelaySettings,
    connect_apns: Callable[[], ApnsSender],
    connect_fcm: Callable[[], FcmSender],
    clock: Clock = utc_now,
) -> FastAPI:
    """The relay app; `connect_apns` and `connect_fcm` run at startup, inside the event loop
    their connections bind to."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = connect_database(settings.database_url)
        await migrate(engine)
        protocol_dir = settings.protocol_dir
        devices = DeviceRegistry(engine, clock)
        events = EventStore(engine, timedelta(days=settings.retention_days))
        fcm = connect_fcm()
        app.state.relay = Relay(
            engine=engine,
            pairing_secret=settings.pairing_secret,
            devices=devices,
            pairing=Pairing(engine, clock, timedelta(seconds=settings.pairing_ttl_seconds)),
            pair_start_limit=RateLimit(PAIR_STARTS_PER_MINUTE, timedelta(minutes=1), clock),
            intake=NotificationIntake(events, connect_apns(), clock),
            replies=ReplyDispatch(ReplyStore(engine), events, devices, fcm, clock),
            reply_limit=RateLimit(REPLIES_PER_MINUTE, timedelta(minutes=1), clock),
            event_parser=BodyParser(protocol_dir, EVENT_SCHEMA),
            pair_start_parser=BodyParser(protocol_dir, PAIR_START_SCHEMA),
            pair_complete_parser=BodyParser(protocol_dir, PAIR_COMPLETE_SCHEMA),
            push_token_parser=BodyParser(protocol_dir, PUSH_TOKEN_SCHEMA),
            watch_push_token_parser=BodyParser(protocol_dir, WATCH_PUSH_TOKEN_SCHEMA),
            reply_parser=BodyParser(protocol_dir, REPLY_SCHEMA),
            result_parser=BodyParser(protocol_dir, RESULT_SCHEMA),
        )
        yield
        await fcm.close()
        await engine.dispose()

    # No /docs, /redoc or /openapi.json: the relay is public, and protocol/ documents the API.
    app = FastAPI(title="Relay", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    for error_type in (ApiError, HTTPException, RequestValidationError, Exception):
        app.add_exception_handler(error_type, answer_error)
    for router in (health, pairing.router, events.router, replies.router):
        app.include_router(router)
    return app


def log_to_stderr() -> None:
    """Shows the relay's own INFO records, such as what became of each reply, next to
    uvicorn's; uvicorn configures only its own loggers."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("relay")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def app_from_env() -> FastAPI:
    """Uvicorn factory: settings from the environment, real APNs and FCM connections."""
    log_to_stderr()
    return create_app(
        RelaySettings(),
        connect_apns=lambda: ApnsSender.connect(ApnsSettings()),
        connect_fcm=lambda: FcmSender.connect(FcmSettings()),
    )
