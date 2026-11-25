"""HTTP API of the relay (docs/TZ.md §9.2): so far notification intake and the health check.

Run with `uvicorn --factory relay.app:app_from_env`; see the README.
"""

import json
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException

from relay.apns import ApnsSender, ApnsSettings, ApnsUnreachable
from relay.database import connect_database, migrate
from relay.events import EVENT_SCHEMA, NotificationEvent
from relay.intake import NotificationIntake
from relay.protocol import BodyParser
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
    event_parser: BodyParser[NotificationEvent]
    intake: NotificationIntake


def current_relay(request: Request) -> Relay:
    relay: Relay = request.app.state.relay
    return relay


CurrentRelay = Annotated[Relay, Depends(current_relay)]


def authenticate(relay: CurrentRelay, authorization: Annotated[str, Header()] = "") -> None:
    """Admits the Companion's static bearer token (pairing replaces it in M2)."""
    scheme, _, token = authorization.partition(" ")
    expected = relay.settings.relay_token.get_secret_value()
    # Bytes, because compare_digest refuses str with non-ASCII characters.
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), expected.encode()):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "invalid_token", "Bearer token required", retryable=False
        )


def as_api_error(error: Exception) -> ApiError:
    """Any error the app answers, in the §5.1 shape; an unexpected one may be retried."""
    match error:
        case ApiError():
            return error
        case HTTPException(status_code=status_code, detail=detail):
            code = HTTPStatus(status_code).phrase.lower().replace(" ", "_")
            return ApiError(status_code, code, str(detail), retryable=False)
        case _:
            return ApiError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "internal_error",
                "Internal Server Error",
                retryable=True,
            )


async def answer_error(_request: Request, error: Exception) -> Response:
    return as_api_error(error).response()


# Largest request body the relay reads (TZ §5.1).
MAX_BODY_BYTES = 32 * 1024


async def read_body(request: Request) -> bytes:
    """The request body; reading stops with 413 as soon as it passes MAX_BODY_BYTES."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise ApiError(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "payload_too_large",
                f"Body over {MAX_BODY_BYTES} bytes",
                retryable=False,
            )
    return bytes(body)


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
        event = relay.event_parser.parse(json.loads(await read_body(request)))
    # Covers malformed JSON, a body that is not UTF-8 and a schema breach.
    except ValueError as error:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "invalid_request", str(error), retryable=False
        ) from error

    try:
        result = await relay.intake.receive(event)
    except ApnsUnreachable as error:
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
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE
            if result.retryable
            else status.HTTP_500_INTERNAL_SERVER_ERROR,
            "apns_rejected",
            f"APNs rejected the push: {result.reason or result.status}",
            retryable=result.retryable,
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
            event_parser=BodyParser(settings.protocol_dir, EVENT_SCHEMA),
            intake=NotificationIntake(store, connect_apns(), settings.watch_push_token),
        )
        yield
        await engine.dispose()

    app = FastAPI(title="Relay", lifespan=lifespan)
    for error_type in (ApiError, HTTPException, Exception):
        app.add_exception_handler(error_type, answer_error)
    app.include_router(router)
    return app


def app_from_env() -> FastAPI:
    """Uvicorn factory: settings from the environment, a real APNs connection."""
    return create_app(RelaySettings(), connect_apns=lambda: ApnsSender.connect(ApnsSettings()))
