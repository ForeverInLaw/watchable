"""Notification events and their APNs deliveries in SQLite (docs/TZ.md §6.1)."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from relay.apns import PushResult
from relay.events import NotificationEvent
from relay.protocol import rfc3339
from relay.tables import deliveries, notification_events


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DISPLAYED = "displayed"


# Characters of body the watch gets; the rest is fetched by id (§5.4).
WATCH_BODY_LIMIT = 3000


@dataclass(frozen=True, slots=True)
class StoredEvent:
    """What a reply needs of its event: where the Companion finds the notification and
    whether it takes a reply."""

    event_id: str
    notification_key: str
    source_package: str
    replyable: bool


class EventStore:
    """Keeps each notification event once and tracks its push to the watch."""

    def __init__(self, engine: AsyncEngine, retention: timedelta) -> None:
        self._engine = engine
        self._retention = retention

    async def add(self, event: NotificationEvent, android_device_id: str, now: datetime) -> None:
        """Stores `event`; an event_id already stored is left as it is."""
        body = event["body"]
        row: dict[str, Any] = {
            "id": event["event_id"],
            "android_device_id": android_device_id,
            "source_package": event["source_package"],
            "source_app": event["source_app"],
            "notification_key": event["notification_key"],
            "group_key": event["group_key"],
            "title": event["title"],
            "body": body[:WATCH_BODY_LIMIT] if body is not None else None,
            "body_full": body,
            "category": event["category"],
            "posted_at": event["posted_at"],
            "replyable": event["replyable"],
            "payload_json": json.dumps(event, ensure_ascii=False),
            "created_at": rfc3339(now),
            "expires_at": rfc3339(now + self._retention),
        }
        async with self._engine.begin() as connection:
            await connection.execute(
                insert(notification_events).values(row).on_conflict_do_nothing()
            )

    async def find(
        self, event_id: str, android_device_id: str, now: datetime
    ) -> StoredEvent | None:
        """The event if `android_device_id` sent it and it has not expired by `now`; None
        alike for an unknown, a foreign and an expired event, so none of them shows."""
        query = select(
            notification_events.c.id,
            notification_events.c.notification_key,
            notification_events.c.source_package,
            notification_events.c.replyable,
        ).where(
            notification_events.c.id == event_id,
            notification_events.c.android_device_id == android_device_id,
            notification_events.c.expires_at > rfc3339(now),
        )
        async with self._engine.connect() as connection:
            row = (await connection.execute(query)).first()
        if row is None:
            return None
        return StoredEvent(row.id, row.notification_key, row.source_package, bool(row.replyable))

    async def was_pushed(self, event_id: str, watch_device_id: str) -> bool:
        """Whether APNs has already accepted this event's push to the watch."""
        query = select(deliveries.c.id).where(
            deliveries.c.event_id == event_id,
            deliveries.c.watch_device_id == watch_device_id,
            deliveries.c.status == DeliveryStatus.SENT,
        )
        async with self._engine.connect() as connection:
            return (await connection.execute(query)).first() is not None

    async def record_push(
        self, event_id: str, watch_device_id: str, result: PushResult, now: datetime
    ) -> None:
        """Records one push attempt and what APNs answered."""
        outcome = {
            "status": DeliveryStatus.SENT if result.ok else DeliveryStatus.FAILED,
            "apns_id": result.apns_id,
            "last_error": result.reason,
            "updated_at": rfc3339(now),
        }
        statement = insert(deliveries).values(
            id=str(uuid.uuid4()),
            event_id=event_id,
            watch_device_id=watch_device_id,
            attempts=1,
            **outcome,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[deliveries.c.event_id, deliveries.c.watch_device_id],
            set_={**outcome, "attempts": deliveries.c.attempts + 1},
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)
