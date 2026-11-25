"""Replies from the watch, kept in SQLite and handed to the Companion over FCM (docs/TZ.md F3)."""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Literal, NoReturn, NotRequired, TypedDict

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from relay.clock import Clock
from relay.devices import DeviceRegistry
from relay.fcm import MAX_DATA_BYTES, FcmSender, FcmUnreachable, envelope, fits_fcm
from relay.protocol import rfc3339
from relay.store import EventStore, StoredEvent
from relay.tables import notification_events, replies

REPLY_SCHEMA = "reply-request.schema.json"
RESULT_SCHEMA = "reply-result.schema.json"
REPLY_EXECUTE = "reply.execute"
# Replies the relay takes from the watch in any minute (§5.1).
REPLIES_PER_MINUTE = 30

# What became of each reply, so an operator can tell why one never reached the chat.
# Never the reply text (§9.7).
log = logging.getLogger(__name__)


class ReplyRequest(TypedDict):
    """Body of POST /v1/events/{event_id}/reply, shaped by protocol/schema/reply-request."""

    reply_id: str
    text: str
    sent_at: str


class ReplyStatus(StrEnum):
    # Handed to FCM; the Companion has not reported the result yet.
    QUEUED = "queued"
    SENT = "sent"
    # FCM did not take the message, or the Companion could not send the reply.
    FAILED = "failed"


class ReplyError(StrEnum):
    """Why a reply failed, as replies.error keeps it (§5.6, §5.10)."""

    # The Companion never sent an FCM token, or FCM called the last one unregistered.
    FCM_TOKEN_MISSING = "fcm_token_missing"
    # FCM refused the message; sending it again will not help.
    FCM_REJECTED = "fcm_rejected"
    # FCM could not be reached or is overloaded; the same reply may be sent again.
    FCM_UNAVAILABLE = "fcm_unavailable"
    # What the Companion reports: the notification has left the shade, or the listener
    # is not connected; or no action of the notification takes free text.
    NOTIFICATION_GONE = "notification_gone"
    REMOTE_INPUT_UNSUPPORTED = "remote_input_unsupported"


class ReplyResult(TypedDict):
    """Body of POST /v1/replies/{reply_id}/result, shaped by protocol/schema/reply-result."""

    status: Literal["sent", "failed"]
    error: NotRequired[Literal["notification_gone", "remote_input_unsupported"]]


class UnknownEvent(Exception):
    """The paired Companion has sent no event with this id, or it has expired."""


class InvalidReply(Exception):
    """The reply cannot go out: the event takes no reply, or the text does not fit FCM.
    The message says which, never the reply text."""


class NoCompanion(Exception):
    """No unrevoked Companion has entered the watch's pairing code."""


class DuplicateReply(Exception):
    """The relay already has this reply: sent to FCM, or with the result reported."""


class UnknownReply(Exception):
    """No reply with this id answers an event of the Companion."""


class Undelivered(Exception):
    """FCM did not take reply.execute; the reply is stored as failed with `reason`.
    The message says what FCM answered, never the reply text."""

    def __init__(self, reason: ReplyError, message: str) -> None:
        super().__init__(message)
        self.reason = reason

    @property
    def retryable(self) -> bool:
        return self.reason is ReplyError.FCM_UNAVAILABLE


class ReplyStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def add(
        self, reply: ReplyRequest, event_id: str, watch_device_id: str, now: datetime
    ) -> bool:
        """Stores `reply` as queued; False when its reply_id is already stored.

        A reply to the same event that FCM was unavailable for is queued again instead,
        as its 503 told the watch that sending it again may help.
        """
        statement = insert(replies).values(
            id=reply["reply_id"],
            event_id=event_id,
            watch_device_id=watch_device_id,
            text=reply["text"],
            status=ReplyStatus.QUEUED,
            created_at=rfc3339(now),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[replies.c.id],
            set_={
                "text": statement.excluded.text,
                "status": ReplyStatus.QUEUED,
                "error": None,
                "completed_at": None,
            },
            where=(replies.c.event_id == event_id)
            & (replies.c.status == ReplyStatus.FAILED)
            & (replies.c.error == ReplyError.FCM_UNAVAILABLE),
        )
        async with self._engine.begin() as connection:
            result = await connection.execute(statement)
        return result.rowcount == 1

    async def complete(
        self, reply_id: str, android_device_id: str, result: ReplyResult, now: datetime
    ) -> None:
        """Records the Companion's result of a queued reply to one of its events.

        Raises UnknownReply alike for an unknown reply and one to another device's event,
        DuplicateReply when the reply is no longer queued.
        """
        own_events = select(notification_events.c.id).where(
            notification_events.c.android_device_id == android_device_id
        )
        owned = (replies.c.id == reply_id) & replies.c.event_id.in_(own_events)
        statement = (
            update(replies)
            .where(owned, replies.c.status == ReplyStatus.QUEUED)
            .values(
                status=ReplyStatus(result["status"]),
                error=result.get("error"),
                completed_at=rfc3339(now),
            )
        )
        async with self._engine.begin() as connection:
            if (await connection.execute(statement)).rowcount == 1:
                return
            known = (await connection.execute(select(replies.c.id).where(owned))).first()
        raise DuplicateReply if known else UnknownReply

    async def fail(self, reply_id: str, reason: ReplyError, now: datetime) -> None:
        statement = (
            update(replies)
            .where(replies.c.id == reply_id)
            .values(status=ReplyStatus.FAILED, error=reason, completed_at=rfc3339(now))
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)


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

    async def send(self, reply: ReplyRequest, event_id: str, watch_device_id: str) -> None:
        """Stores `reply` as queued and hands reply.execute to FCM.

        Raises NoCompanion, UnknownEvent or InvalidReply before anything is stored,
        DuplicateReply when the reply_id is already stored, and Undelivered once the
        reply is stored as failed because FCM did not take it.
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
            raise InvalidReply("The event takes no reply")
        message = reply_execute(reply, event, watch_device_id, now)
        if not fits_fcm(message):
            raise InvalidReply(f"The reply does not fit {MAX_DATA_BYTES} bytes of FCM data")
        if not await self._store.add(reply, event_id, watch_device_id, now):
            raise DuplicateReply
        reply_id = reply["reply_id"]
        if companion.fcm_token is None:
            await self._fail(
                reply_id, ReplyError.FCM_TOKEN_MISSING, "The Companion has no FCM token"
            )
        try:
            result = await self._fcm.send(companion.fcm_token, message)
        except FcmUnreachable:
            await self._fail(reply_id, ReplyError.FCM_UNAVAILABLE, "FCM unreachable")
        if result.ok:
            log.info("reply %s to event %s: handed to FCM", reply_id, event_id)
            return
        if result.unregistered:
            await self._devices.drop_push_token(companion.device_id, companion.fcm_token)
        reason = ReplyError.FCM_UNAVAILABLE if result.retryable else ReplyError.FCM_REJECTED
        await self._fail(reply_id, reason, f"FCM answered {result.status} {result.error}")

    async def complete(self, reply_id: str, android_device_id: str, result: ReplyResult) -> None:
        """Records what the Companion made of the reply; raises as ReplyStore.complete."""
        await self._store.complete(reply_id, android_device_id, result, self._clock())
        log.info("reply %s: %s %s", reply_id, result["status"], result.get("error", ""))

    async def _fail(self, reply_id: str, reason: ReplyError, message: str) -> NoReturn:
        await self._store.fail(reply_id, reason, self._clock())
        log.warning("reply %s: failed %s (%s)", reply_id, reason, message)
        raise Undelivered(reason, message)
