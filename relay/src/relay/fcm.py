"""FCM HTTP v1 delivery of envelopes to the Companion (docs/TZ.md §5.3, §9.4)."""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

import google.auth.exceptions
import google.auth.transport
import google.auth.transport.requests
import httpx2
from google.oauth2 import service_account
from pydantic import FilePath
from pydantic_settings import BaseSettings, SettingsConfigDict

from relay.protocol import rfc3339

# OAuth2 scope of the FCM HTTP v1 API.
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
# How long FCM keeps a message for an offline phone (§9.4).
TTL = "3600s"
# Envelope v; FCM data holds only strings (§5.3).
ENVELOPE_VERSION = "1"
# FCM error codes that a later send can get past (FCM's error code reference).
TRANSIENT_ERRORS = frozenset({"QUOTA_EXCEEDED", "UNAVAILABLE", "INTERNAL"})
# FCM refuses a message whose data keys and values together pass this many UTF-8 bytes.
MAX_DATA_BYTES = 4096


def fits_fcm(data: Mapping[str, str]) -> bool:
    """Whether FCM takes `data` as it counts size: keys and values in UTF-8."""
    size = sum(len(key.encode()) + len(value.encode()) for key, value in data.items())
    return size <= MAX_DATA_BYTES


class FcmSettings(BaseSettings):
    """The Firebase project and its service account JSON, from FCM_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="FCM_")

    project_id: str
    service_account_path: FilePath


class AccessTokens(Protocol):
    async def get(self) -> str: ...


class ServiceAccountTokens:
    """OAuth2 access tokens of a service account. google-auth keeps each one until shortly
    before it expires; `transport` is what fetches a new one from Google's token endpoint."""

    def __init__(
        self, credentials: service_account.Credentials, transport: google.auth.transport.Request
    ) -> None:
        self._credentials = credentials
        self._transport = transport
        # One fetch at a time: concurrent sends share the token it brings.
        self._lock = asyncio.Lock()

    @classmethod
    def from_file(cls, path: FilePath) -> Self:
        credentials = service_account.Credentials.from_service_account_file(
            str(path), scopes=[FCM_SCOPE]
        )
        return cls(credentials, google.auth.transport.requests.Request())

    async def get(self) -> str:
        async with self._lock:
            if not self._credentials.valid:
                # google-auth fetches synchronously; off the event loop it blocks nothing else.
                await asyncio.to_thread(self._credentials.refresh, self._transport)
            token = self._credentials.token
            if not isinstance(token, str):
                raise google.auth.exceptions.RefreshError("No access token after a refresh")
            return token


@dataclass(frozen=True, slots=True)
class FcmResult:
    """FCM's answer to one message: the HTTP status and, on rejection, FCM's error code,
    such as UNREGISTERED or QUOTA_EXCEEDED."""

    status: int
    error: str | None

    @property
    def ok(self) -> bool:
        return self.status == 200

    @property
    def retryable(self) -> bool:
        """FCM is overloaded or failing for now; the same message may go through later."""
        return self.error in TRANSIENT_ERRORS or self.status == 429 or self.status >= 500

    @property
    def unregistered(self) -> bool:
        """The registration token is no longer valid; FCM wants it dropped."""
        return self.error == "UNREGISTERED"


class FcmUnreachable(Exception):
    """The relay could not reach FCM or Google's token endpoint; nothing was sent."""


def envelope(
    type_: str, id_: str, sent_at: datetime, device_id: str, payload: Mapping[str, Any]
) -> dict[str, str]:
    """The envelope as FCM data: `v` a string and `payload` its JSON text (§5.3)."""
    return {
        "v": ENVELOPE_VERSION,
        "id": id_,
        "type": type_,
        "sent_at": rfc3339(sent_at),
        "device_id": device_id,
        "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


class FcmSender:
    """Sends data messages to Companion FCM tokens over one reusable HTTP client."""

    def __init__(self, http: httpx2.AsyncClient, tokens: AccessTokens, project_id: str) -> None:
        self._http = http
        self._tokens = tokens
        self._url = SEND_URL.format(project_id=project_id)

    @classmethod
    def connect(cls, settings: FcmSettings) -> Self:
        tokens = ServiceAccountTokens.from_file(settings.service_account_path)
        return cls(httpx2.AsyncClient(), tokens, settings.project_id)

    async def send(self, registration_token: str, data: Mapping[str, str]) -> FcmResult:
        """Delivers `data` at high priority: every message so far is one the user waits on.

        Raises FcmUnreachable when FCM or the token endpoint cannot be reached.
        """
        message = {
            "token": registration_token,
            "data": dict(data),
            "android": {"priority": "high", "ttl": TTL},
        }
        try:
            response = await self._http.post(
                self._url,
                json={"message": message},
                headers={"Authorization": f"Bearer {await self._tokens.get()}"},
            )
        except (httpx2.HTTPError, google.auth.exceptions.TransportError) as error:
            raise FcmUnreachable from error
        if response.status_code == 200:
            return FcmResult(status=200, error=None)
        return FcmResult(status=response.status_code, error=error_code(response))

    async def close(self) -> None:
        await self._http.aclose()


def error_code(response: httpx2.Response) -> str | None:
    """FCM's errorCode from the error details, else the Google API status; None without a body."""
    try:
        error = response.json().get("error") or {}
    except ValueError:
        return None
    for detail in error.get("details", []):
        if "errorCode" in detail:
            code: str = detail["errorCode"]
            return code
    status: str | None = error.get("status")
    return status
