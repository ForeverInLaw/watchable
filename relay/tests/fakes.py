import asyncio
import functools
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import google.auth.transport
from aioapns import NotificationRequest
from aioapns.common import NotificationResult
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class FakeApnsClient:
    """Stands in for aioapns.APNs: records the request, answers with a canned result
    or, when `error` is set, raises it. `delay` holds each answer back, like the network."""

    def __init__(self, result: NotificationResult) -> None:
        self.result = result
        self.error: Exception | None = None
        self.delay = 0.0
        self.requests: list[NotificationRequest] = []

    async def send_notification(self, request: NotificationRequest) -> NotificationResult:
        self.requests.append(request)
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.result


@functools.cache
def service_account_info() -> dict[str, str]:
    """A service account JSON as the Firebase console issues it, with a fresh RSA key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return {
        "type": "service_account",
        "project_id": "watch-app",
        "private_key_id": "key-1",
        "private_key": pem.decode(),
        "client_email": "relay@watch-app.iam.gserviceaccount.com",
        "client_id": "1",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


@dataclass(frozen=True, slots=True)
class TokenResponse(google.auth.transport.Response):
    status: int
    headers: dict[str, str]
    data: bytes


class FakeTokenEndpoint(google.auth.transport.Request):
    """Stands in for Google's OAuth2 token endpoint: every request gets a new access token
    that lasts `expires_in` seconds."""

    def __init__(self, expires_in: int) -> None:
        self.expires_in = expires_in
        self.requests = 0

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> TokenResponse:
        self.requests += 1
        token = {"access_token": f"access-token-{self.requests}", "expires_in": self.expires_in}
        return TokenResponse(200, {}, json.dumps(token).encode())


class FakeTokens:
    """An access token source that always has `token`."""

    def __init__(self, token: str) -> None:
        self.token = token

    async def get(self) -> str:
        return self.token


class FakeClock:
    """A clock that stands still until a test moves it."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
