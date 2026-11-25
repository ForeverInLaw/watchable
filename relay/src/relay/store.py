"""Notification events and their APNs deliveries in SQLite (docs/TZ.md §6.1)."""

import json
import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from relay.apns import PushResult
from relay.events import NotificationEvent
from relay.protocol import rfc3339

metadata = MetaData()


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DISPLAYED = "displayed"


notification_events = Table(
    "notification_events",
    metadata,
    Column("id", Text, primary_key=True),
    Column("android_device_id", Text, nullable=False),
    Column("source_package", Text, nullable=False),
    Column("source_app", Text),
    Column("notification_key", Text, nullable=False),
    Column("group_key", Text),
    Column("title", Text),
    # body is what the watch gets (§5.4), body_full the text the Companion sent.
    Column("body", Text),
    Column("body_full", Text),
    Column("category", Text),
    Column("posted_at", Text, nullable=False),
    Column("replyable", Integer, nullable=False, server_default="0"),
    Column("payload_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Index("ix_notification_events_android_device_id_created_at", "android_device_id", "created_at"),
)

deliveries = Table(
    "deliveries",
    metadata,
    Column("id", Text, primary_key=True),
    Column("event_id", Text, ForeignKey("notification_events.id"), nullable=False),
    Column("watch_device_id", Text, nullable=False),
    # A DeliveryStatus value.
    Column("status", Text, nullable=False),
    Column("apns_id", Text),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", Text),
    Column("next_attempt_at", Text),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint("event_id", "watch_device_id"),
    Index("ix_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
)

# Characters of body the watch gets; the rest is fetched by id (§5.4).
WATCH_BODY_LIMIT = 3000


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
