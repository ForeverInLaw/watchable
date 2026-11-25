"""Pairing of the watch and the Companion by a one-time code (docs/TZ.md F1, §5.2)."""

import asyncio
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, NotRequired, TypedDict

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from relay.clock import Clock
from relay.devices import DeviceRole, add_device, token_hash
from relay.protocol import rfc3339
from relay.tables import devices, pairing_sessions

PAIR_START_SCHEMA = "pair-start-request.schema.json"
PAIR_COMPLETE_SCHEMA = "pair-complete-request.schema.json"
CODE_DIGITS = 8
# Wrong codes that burn the open session (§5.2).
MAX_FAILED_ATTEMPTS = 5


class PairStartRequest(TypedDict):
    """Body of POST /v1/pair/start, shaped by protocol/schema/pair-start-request."""

    platform: Literal["watchos"]
    apns_token: str
    name: NotRequired[str]


class PairCompleteRequest(TypedDict):
    """Body of POST /v1/pair/complete, shaped by protocol/schema/pair-complete-request."""

    pairing_code: str
    platform: Literal["android"]
    fcm_token: NotRequired[str]
    name: NotRequired[str]


@dataclass(frozen=True, slots=True)
class StartedPairing:
    """The answer to pair/start, shaped by protocol/schema/pair-start-response."""

    pairing_id: str
    pairing_code: str
    watch_device_id: str
    watch_device_token: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class CompletedPairing:
    """The answer to pair/complete, shaped by protocol/schema/pair-complete-response."""

    android_device_id: str
    android_device_token: str
    watch_device_id: str


class InvalidPairingCode(Exception):
    """The code is wrong, expired, used or burned; the reason is not told apart."""


class PairingExpired(Exception):
    """The session expired, burned or was replaced; the watch starts a new one."""


class Pairing:
    """One open session at a time: the watch starts it, the Companion completes it."""

    def __init__(self, engine: AsyncEngine, clock: Clock, ttl: timedelta) -> None:
        self._engine = engine
        self._clock = clock
        self._ttl = ttl
        # Sessions change one request at a time, so two correct codes cannot both win.
        self._lock = asyncio.Lock()

    async def start(self, apns_token: str, name: str | None) -> StartedPairing:
        """Creates the watch device and a new session; the open one is closed."""
        now = self._clock()
        code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
        pairing_id = str(uuid.uuid4())
        expires_at = rfc3339(now + self._ttl)
        async with self._lock, self._engine.begin() as connection:
            await connection.execute(
                update(pairing_sessions)
                .where(pairing_sessions.c.used_at.is_(None), pairing_sessions.c.closed_at.is_(None))
                .values(closed_at=rfc3339(now))
            )
            watch_id, watch_token = await add_device(
                connection, DeviceRole.WATCH, name=name, push_token=apns_token, now=now
            )
            await connection.execute(
                insert(pairing_sessions).values(
                    id=pairing_id,
                    watch_device_id=watch_id,
                    code_hash=token_hash(code),
                    created_at=rfc3339(now),
                    expires_at=expires_at,
                )
            )
        return StartedPairing(pairing_id, code, watch_id, watch_token, expires_at)

    async def is_paired(self, pairing_id: str, watch_device_id: str) -> bool:
        """Whether the Companion has entered the code of the watch's session.

        Raises PairingExpired once the session can no longer be completed.
        """
        query = select(
            pairing_sessions.c.used_at, pairing_sessions.c.closed_at, pairing_sessions.c.expires_at
        ).where(
            pairing_sessions.c.id == pairing_id,
            pairing_sessions.c.watch_device_id == watch_device_id,
        )
        async with self._engine.connect() as connection:
            session = (await connection.execute(query)).first()
        if session is None:
            raise PairingExpired
        if session.used_at is not None:
            return True
        if session.closed_at is not None or session.expires_at <= rfc3339(self._clock()):
            raise PairingExpired
        return False

    async def complete(
        self, code: str, fcm_token: str | None, name: str | None
    ) -> CompletedPairing:
        """Pairs a new Companion with the watch of the open session.

        Every other device is revoked, so a re-pair drops the old phone and watch.
        A wrong code counts against the session and raises InvalidPairingCode.
        """
        now = self._clock()
        async with self._lock:
            async with self._engine.begin() as connection:
                query = select(
                    pairing_sessions.c.id,
                    pairing_sessions.c.watch_device_id,
                    pairing_sessions.c.code_hash,
                    pairing_sessions.c.failed_attempts,
                ).where(
                    pairing_sessions.c.used_at.is_(None),
                    pairing_sessions.c.closed_at.is_(None),
                    pairing_sessions.c.expires_at > rfc3339(now),
                )
                session = (await connection.execute(query)).first()
                if session is None:
                    raise InvalidPairingCode
                if secrets.compare_digest(session.code_hash, token_hash(code)):
                    return await self._pair(
                        connection, session.id, session.watch_device_id, fcm_token, name, now
                    )
                # Counted before raising, so the rollback cannot undo it.
                failed_attempts = session.failed_attempts + 1
                await connection.execute(
                    update(pairing_sessions)
                    .where(pairing_sessions.c.id == session.id)
                    .values(
                        failed_attempts=failed_attempts,
                        closed_at=rfc3339(now) if failed_attempts >= MAX_FAILED_ATTEMPTS else None,
                    )
                )
            raise InvalidPairingCode

    @staticmethod
    async def _pair(
        connection: AsyncConnection,
        pairing_id: str,
        watch_device_id: str,
        fcm_token: str | None,
        name: str | None,
        now: datetime,
    ) -> CompletedPairing:
        android_id, android_token = await add_device(
            connection, DeviceRole.ANDROID, name=name, push_token=fcm_token, now=now
        )
        await connection.execute(
            update(pairing_sessions)
            .where(pairing_sessions.c.id == pairing_id)
            .values(used_at=rfc3339(now), android_device_id=android_id)
        )
        await connection.execute(
            update(devices)
            .where(
                devices.c.revoked_at.is_(None),
                devices.c.id.not_in([android_id, watch_device_id]),
            )
            .values(revoked_at=rfc3339(now))
        )
        return CompletedPairing(android_id, android_token, watch_device_id)
