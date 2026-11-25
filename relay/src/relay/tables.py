"""The relay's SQLite tables (docs/TZ.md §6.1); Alembic revisions are generated from them."""

from sqlalchemy import Column, ForeignKey, Index, Integer, MetaData, Table, Text, UniqueConstraint

metadata = MetaData()


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

replies = Table(
    "replies",
    metadata,
    # The reply_id the watch generated.
    Column("id", Text, primary_key=True),
    Column("event_id", Text, ForeignKey("notification_events.id"), nullable=False),
    Column("watch_device_id", Text, nullable=False),
    Column("text", Text, nullable=False),
    # A ReplyStatus value.
    Column("status", Text, nullable=False),
    Column("error", Text),
    Column("created_at", Text, nullable=False),
    Column("completed_at", Text),
)

devices = Table(
    "devices",
    metadata,
    Column("id", Text, primary_key=True),
    # A DeviceRole value.
    Column("role", Text, nullable=False),
    Column("name", Text),
    Column("platform", Text, nullable=False),
    # APNs device token of the watch, FCM registration token of the Companion.
    Column("push_token", Text),
    # SHA-256 of the Bearer token; the token itself is never stored.
    Column("token_hash", Text, nullable=False, unique=True),
    Column("created_at", Text, nullable=False),
    Column("last_seen_at", Text),
    Column("revoked_at", Text),
)

pairing_sessions = Table(
    "pairing_sessions",
    metadata,
    Column("id", Text, primary_key=True),
    Column("watch_device_id", Text, ForeignKey("devices.id"), nullable=False),
    Column("code_hash", Text, nullable=False),
    # Wrong codes entered while the session is open; MAX_FAILED_ATTEMPTS closes it.
    Column("failed_attempts", Integer, nullable=False, server_default="0"),
    # Set with used_at, once the Companion has entered the code.
    Column("android_device_id", Text, ForeignKey("devices.id")),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("used_at", Text),
    # When a newer pair/start replaced the session or wrong codes burned it.
    Column("closed_at", Text),
)
