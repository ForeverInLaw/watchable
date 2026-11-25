"""What every route shares: the §5.1 error shape, body parsing and Bearer authentication."""

import json
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException

from relay.devices import Device, DeviceRegistry, DeviceRole, PushTokenRequest
from relay.events import NotificationEvent
from relay.intake import NotificationIntake
from relay.pairing import PairCompleteRequest, Pairing, PairStartRequest
from relay.protocol import BodyParser
from relay.ratelimit import RateLimit
from relay.replies import ReplyDispatch, ReplyRequest


class ApiError(Exception):
    """An error answered in the §5.1 shape: {"error": {code, message, retryable}}.

    `retry_after` (seconds) goes out as the Retry-After header of a 429 (§5.10).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after

    def response(self) -> JSONResponse:
        error = {"code": self.code, "message": self.message, "retryable": self.retryable}
        headers = None if self.retry_after is None else {"Retry-After": str(self.retry_after)}
        return JSONResponse({"error": error}, status_code=self.status_code, headers=headers)


def invalid_token() -> ApiError:
    """401 for a missing, unknown, revoked or misplaced Bearer token; the client re-pairs."""
    return ApiError(
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
        # A missing or malformed query parameter; the details would echo the request.
        case RequestValidationError():
            return ApiError(
                status.HTTP_400_BAD_REQUEST,
                "invalid_request",
                "Invalid request parameters",
                retryable=False,
            )
        case _:
            return ApiError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "internal_error",
                "Internal Server Error",
                retryable=True,
            )


async def answer_error(_request: Request, error: Exception) -> Response:
    return as_api_error(error).response()


@dataclass(frozen=True, slots=True)
class Relay:
    """What the routes use, built once per app run inside its event loop."""

    engine: AsyncEngine
    pairing_secret: SecretStr
    devices: DeviceRegistry
    pairing: Pairing
    pair_start_limit: RateLimit
    intake: NotificationIntake
    replies: ReplyDispatch
    reply_limit: RateLimit
    event_parser: BodyParser[NotificationEvent]
    pair_start_parser: BodyParser[PairStartRequest]
    pair_complete_parser: BodyParser[PairCompleteRequest]
    push_token_parser: BodyParser[PushTokenRequest]
    watch_push_token_parser: BodyParser[PushTokenRequest]
    reply_parser: BodyParser[ReplyRequest]


def current_relay(request: Request) -> Relay:
    relay: Relay = request.app.state.relay
    return relay


CurrentRelay = Annotated[Relay, Depends(current_relay)]


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


async def parse_body[T](request: Request, parser: BodyParser[T]) -> T:
    """The JSON body checked against its schema; 400 when it is not JSON or breaks it."""
    try:
        return parser.parse(json.loads(await read_body(request)))
    # Covers malformed JSON, a body that is not UTF-8 and a schema breach.
    except ValueError as error:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "invalid_request", str(error), retryable=False
        ) from error


def bearer_token(authorization: Annotated[str, Header()] = "") -> str | None:
    """The credential of an `Authorization: Bearer <credential>` header, if one came."""
    scheme, _, credential = authorization.partition(" ")
    return credential if scheme.lower() == "bearer" else None


BearerToken = Annotated[str | None, Depends(bearer_token)]


async def authenticate(relay: CurrentRelay, token: BearerToken) -> Device:
    """The device whose Bearer token came with the request."""
    device = None if token is None else await relay.devices.authenticate(token)
    if device is None:
        raise invalid_token()
    return device


CurrentDevice = Annotated[Device, Depends(authenticate)]


def require_android(device: CurrentDevice) -> Device:
    """Only the Companion sends what Android produces; any other token is refused."""
    if device.role is not DeviceRole.ANDROID:
        raise invalid_token()
    return device


CurrentAndroid = Annotated[Device, Depends(require_android)]


def require_watch(device: CurrentDevice) -> Device:
    """Only the watch sends what the user does on the watch; any other token is refused."""
    if device.role is not DeviceRole.WATCH:
        raise invalid_token()
    return device


CurrentWatch = Annotated[Device, Depends(require_watch)]


def require_pairing_secret(relay: CurrentRelay, secret: BearerToken) -> None:
    """Admits pair/start only with the PAIRING_SECRET the watch build carries."""
    # Bytes, because compare_digest refuses str with non-ASCII characters.
    expected = relay.pairing_secret.get_secret_value().encode()
    if secret is None or not secrets.compare_digest(secret.encode(), expected):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_pairing_secret",
            "Pairing secret required",
            retryable=False,
        )
