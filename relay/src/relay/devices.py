"""Paired devices and their Bearer tokens (docs/TZ.md §5.2, §6.1)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypedDict

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from relay.clock import Clock
from relay.protocol import rfc3339
from relay.tables import devices, pairing_sessions

PUSH_TOKEN_SCHEMA = "push-token-request.schema.json"


class DeviceRole(StrEnum):
    ANDROID = "android"
    WATCH = "watchos"


@dataclass(frozen=True, slots=True)
class Device:
    """A device holding a valid Bearer token."""

    id: str
    role: DeviceRole


@dataclass(frozen=True, slots=True)
class PushTarget:
    """Where the relay pushes for a device: its id and its APNs or FCM token."""

    device_id: str
    push_token: str


class PushTokenRequest(TypedDict):
    """Body of POST /v1/devices/{id}/push-token, shaped by protocol/schema/push-token-request."""

    push_token: str


def token_hash(secret: str) -> str:
    """What the relay keeps of a device token or pairing code: its SHA-256, in hex."""
    return hashlib.sha256(secret.encode()).hexdigest()


async def add_device(
    connection: AsyncConnection,
    role: DeviceRole,
    *,
    name: str | None,
    push_token: str | None,
    now: datetime,
) -> tuple[str, str]:
    """Creates a device in the caller's transaction; returns its id and Bearer token.

    The token is 32 random bytes in base64url; only its hash is stored.
    """
    device_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    await connection.execute(
        insert(devices).values(
            id=device_id,
            role=role,
            name=name,
            platform=role,
            push_token=push_token,
            token_hash=token_hash(token),
            created_at=rfc3339(now),
        )
    )
    return device_id, token


class DeviceRegistry:
    """Authenticates Bearer tokens and keeps each device's push token."""

    def __init__(self, engine: AsyncEngine, clock: Clock) -> None:
        self._engine = engine
        self._clock = clock

    async def authenticate(self, token: str) -> Device | None:
        """The device `token` belongs to, unless revoked; marks it seen now."""
        statement = (
            update(devices)
            .where(devices.c.token_hash == token_hash(token), devices.c.revoked_at.is_(None))
            .values(last_seen_at=rfc3339(self._clock()))
            .returning(devices.c.id, devices.c.role)
        )
        async with self._engine.begin() as connection:
            row = (await connection.execute(statement)).first()
        return None if row is None else Device(row.id, DeviceRole(row.role))

    async def set_push_token(self, device_id: str, push_token: str) -> None:
        statement = update(devices).where(devices.c.id == device_id).values(push_token=push_token)
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def paired_watch(self, android_device_id: str) -> PushTarget | None:
        """The watch the Companion paired with, unless it is revoked or has no push token."""
        query = (
            select(devices.c.id, devices.c.push_token)
            .join(pairing_sessions, pairing_sessions.c.watch_device_id == devices.c.id)
            .where(
                pairing_sessions.c.android_device_id == android_device_id,
                devices.c.revoked_at.is_(None),
                devices.c.push_token.is_not(None),
            )
        )
        async with self._engine.connect() as connection:
            row = (await connection.execute(query)).first()
        return None if row is None else PushTarget(row.id, row.push_token)
