"""Notification events from the Companion (docs/TZ.md §5.4) and the alert each becomes."""

from pathlib import Path
from typing import Literal, TypedDict, cast

from relay.apns import AlertPush
from relay.protocol import schema_validator

EVENT_SCHEMA = "notification-event.schema.json"


class Action(TypedDict):
    id: str
    title: str
    type: Literal["text"]


class NotificationEvent(TypedDict):
    """Body of POST /v1/events/notification, shaped by protocol/schema/notification-event."""

    event_id: str
    source_package: str
    source_app: str | None
    notification_key: str
    group_key: str | None
    posted_at: str
    title: str | None
    body: str | None
    subtext: str | None
    category: str | None
    is_ongoing: bool
    is_clearable: bool
    is_group_summary: bool
    replyable: bool
    actions: list[Action]


class InvalidEvent(ValueError):
    """The body breaks the schema. The message names the rule, never the offending value."""


class EventParser:
    """Checks request bodies against the Notification event schema in protocol/."""

    def __init__(self, protocol_dir: Path) -> None:
        self._validator = schema_validator(protocol_dir, EVENT_SCHEMA)

    def parse(self, body: object) -> NotificationEvent:
        error = next(self._validator.iter_errors(body), None)
        if error is not None:
            raise InvalidEvent(f"{error.json_path} fails {error.validator}")
        # The schema has just proven the shape the TypedDict describes.
        return cast(NotificationEvent, body)


# Between the app and the sender in the alert title, as in "Telegram · Alice".
TITLE_SEPARATOR = " · "


def alert_push(event: NotificationEvent) -> AlertPush:
    """The watch alert: the title names the app and, when known, the sender."""
    app = event["source_app"] or event["source_package"]
    sender = event["title"]
    return AlertPush(
        title=f"{app}{TITLE_SEPARATOR}{sender}" if sender else app,
        body=event["body"],
        source_package=event["source_package"],
        event_id=event["event_id"],
        replyable=event["replyable"],
    )
