"""Notification intake: keep each event once and push it to the watch until APNs accepts."""

from datetime import UTC, datetime

from relay.apns import DEFAULT_TTL_SECONDS, ApnsSender, PushResult
from relay.events import NotificationEvent, alert_push
from relay.store import EventStore

# Until pairing (M2) the relay serves exactly one Companion and one watch.
ANDROID_DEVICE_ID = "android"
WATCH_DEVICE_ID = "watch"


class NotificationIntake:
    def __init__(self, store: EventStore, sender: ApnsSender, watch_push_token: str) -> None:
        self._store = store
        self._sender = sender
        self._watch_push_token = watch_push_token

    async def receive(self, event: NotificationEvent) -> PushResult | None:
        """Stores `event` and pushes it; None when APNs has already accepted it.

        An event whose push failed is pushed again when the Companion resends it,
        so a retry after an APNs error is never lost as a duplicate.
        Raises aioapns MaxAttemptsExceeded when APNs is unreachable.
        """
        await self._store.add(event, ANDROID_DEVICE_ID, datetime.now(UTC))
        if await self._store.was_pushed(event["event_id"], WATCH_DEVICE_ID):
            return None
        result = await self._sender.send(
            self._watch_push_token, alert_push(event), DEFAULT_TTL_SECONDS
        )
        await self._store.record_push(event["event_id"], WATCH_DEVICE_ID, result, datetime.now(UTC))
        return result
