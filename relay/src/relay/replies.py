"""Replies from the watch, kept in SQLite and handed to the Companion over FCM (docs/TZ.md F3)."""

from datetime import datetime
from enum import StrEnum
from typing import TypedDict

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from relay.clock import Clock
from relay.devices import DeviceRegistry
from relay.fcm import FcmResult, FcmSender, envelope
from relay.protocol import rfc3339
from relay.store import EventStore, StoredEvent
from relay.tables import replies

REPLY_SCHEMA = "reply-request.schema.json"
REPLY_EXECUTE = "reply.execute"


class ReplyRequest(TypedDict):
    """Body of POST /v1/events/{event_id}/reply, shaped by protocol/schema/reply-request."""

    reply_id: str
    text: str
    sent_at: str


class ReplyStatus(StrEnum):
    # Handed to FCM; the Companion has not reported the result yet.
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class UnknownEvent(Exception):
    """The paired Companion has sent no event with this id, or it has expired."""


class NotReplyable(Exception):
    """The event's notification has no action that takes a reply."""


class NoCompanion(Exception):
    """No unrevoked Companion has entered the watch's pairing code."""


class NoFcmToken(Exception):
    """The paired Companion has not sent its FCM token yet."""


class ReplyStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def add(
        self, reply: ReplyRequest, event_id: str, watch_device_id: str, now: datetime
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                insert(replies).values(
                    id=reply["reply_id"],
                    event_id=event_id,
                    watch_device_id=watch_device_id,
                    text=reply["text"],
                    status=ReplyStatus.QUEUED,
                    created_at=rfc3339(now),
                )
            )


def reply_execute(
    reply: ReplyRequest, event: StoredEvent, watch_device_id: str, now: datetime
) -> dict[str, str]:
    """The reply.execute envelope (§5.6); its id is the reply_id until the outbox (M6)."""
    payload = {
        "reply_id": reply["reply_id"],
        "event_id": event.event_id,
        "notification_key": event.notification_key,
        "source_package": event.source_package,
        "text": reply["text"],
    }
    return envelope(REPLY_EXECUTE, reply["reply_id"], now, watch_device_id, payload)


class ReplyDispatch:
    """Keeps each reply and sends it to the paired Companion in the same request, as the
    relay pushes alerts to the watch: there is no outbox before M6."""

    def __init__(
        self,
        store: ReplyStore,
        events: EventStore,
        devices: DeviceRegistry,
        fcm: FcmSender,
        clock: Clock,
    ) -> None:
        self._store = store
        self._events = events
        self._devices = devices
        self._fcm = fcm
        self._clock = clock

    async def send(self, reply: ReplyRequest, event_id: str, watch_device_id: str) -> FcmResult:
        """Stores `reply` as queued and hands reply.execute to FCM; FcmResult is FCM's answer.

        Raises NoCompanion, UnknownEvent, NotReplyable or NoFcmToken before anything is stored.
        """
        companion = await self._devices.paired_companion(watch_device_id)
        if companion is None:
            raise NoCompanion
        now = self._clock()
        # Scoped to the Companion, so the answer does not tell which other event ids exist.
        event = await self._events.find(event_id, companion.device_id, now)
        if event is None:
            raise UnknownEvent
        if not event.replyable:
            raise NotReplyable
        if companion.fcm_token is None:
            raise NoFcmToken
        await self._store.add(reply, event_id, watch_device_id, now)
        message = reply_execute(reply, event, watch_device_id, now)
        return await self._fcm.send(companion.fcm_token, message)
