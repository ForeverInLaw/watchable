"""Notification events from the Companion (docs/TZ.md §5.4) and the alert each becomes."""

from typing import Literal, TypedDict

from relay.apns import AlertPush

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
