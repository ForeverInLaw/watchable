"""HTTP API of the relay (docs/TZ.md §9.2): so far notification intake and the health check.

Run with `uvicorn --factory relay.app:app_from_env`; see the README.
"""

import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from json import JSONDecodeError
from typing import Annotated

from aioapns.exceptions import MaxAttemptsExceeded
from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from relay.apns import ApnsSender, ApnsSettings
from relay.database import connect_database, migrate
from relay.events import EventParser, InvalidEvent
from relay.intake import NotificationIntake
from relay.settings import RelaySettings
from relay.store import EventStore


class ApiError(Exception):
    """An error answered in the §5.1 shape: {"error": {code, message, retryable}}."""

    def __init__(self, status_code: int, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable

    def response(self) -> JSONResponse:
        error = {"code": self.code, "message": self.message, "retryable": self.retryable}
        return JSONResponse({"error": error}, status_code=self.status_code)


@dataclass(frozen=True, slots=True)
class Relay:
    """What the routes use, built once per app run inside its event loop."""

    settings: RelaySettings
    engine: AsyncEngine
    parser: EventParser
    intake: NotificationIntake


def current_relay(request: Request) -> Relay:
    relay: Relay = request.app.state.relay
    return relay


CurrentRelay = Annotated[Relay, Depends(current_relay)]


def authenticate(relay: CurrentRelay, authorization: Annotated[str, Header()] = "") -> None:
    """Admits the Companion's static bearer token (pairing replaces it in M2)."""
    scheme, _, token = authorization.partition(" ")
    expected = relay.settings.relay_token.get_secret_value()
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "invalid_token", "Bearer token required", retryable=False
        )


async def answer_api_error(_request: Request, error: Exception) -> Response:
    """Registered for ApiError only; Starlette types every handler for Exception."""
    assert isinstance(error, ApiError)
    return error.response()


router = APIRouter()


@router.get("/healthz")
async def healthz(relay: CurrentRelay) -> dict[str, str]:
    async with relay.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.post(
    "/v1/events/notification",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(authenticate)],
)
async def receive_notification(request: Request, relay: CurrentRelay) -> Response:
    """Stores the event and pushes it to the watch; 202 once APNs accepts the push."""
    try:
        event = relay.parser.parse(await request.json())
    except (JSONDecodeError, InvalidEvent) as error:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "invalid_request", str(error), retryable=False
        ) from error

    try:
        result = await relay.intake.receive(event)
    except MaxAttemptsExceeded as error:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "apns_unavailable",
            "APNs unreachable",
            retryable=True,
        ) from error

    if result is None:
        raise ApiError(
            status.HTTP_409_CONFLICT, "duplicate", "Event already delivered", retryable=False
        )
    if not result.ok:
        # Throttling and APNs outages pass; a rejected token or payload does not.
        retryable = result.status == status.HTTP_429_TOO_MANY_REQUESTS or result.status >= 500
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE
            if retryable
            else status.HTTP_500_INTERNAL_SERVER_ERROR,
            "apns_rejected",
            f"APNs rejected the push: {result.reason or result.status}",
            retryable=retryable,
        )
    return Response(status_code=status.HTTP_202_ACCEPTED)


def create_app(settings: RelaySettings, connect_apns: Callable[[], ApnsSender]) -> FastAPI:
    """The relay app; `connect_apns` runs at startup, inside the event loop aioapns needs."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = connect_database(settings.database_url)
        await migrate(engine)
        store = EventStore(engine, timedelta(days=settings.retention_days))
        app.state.relay = Relay(
            settings=settings,
            engine=engine,
            parser=EventParser(settings.protocol_dir),
            intake=NotificationIntake(store, connect_apns(), settings.watch_push_token),
        )
        yield
        await engine.dispose()

    app = FastAPI(title="Relay", lifespan=lifespan)
    app.add_exception_handler(ApiError, answer_api_error)
    app.include_router(router)
    return app


def app_from_env() -> FastAPI:
    """Uvicorn factory: settings from the environment, a real APNs connection."""
    return create_app(RelaySettings(), connect_apns=lambda: ApnsSender.connect(ApnsSettings()))
