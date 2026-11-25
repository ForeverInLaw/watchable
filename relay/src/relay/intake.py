"""Notification intake: keep each event once and push it to the watch until APNs accepts."""

import asyncio
from datetime import UTC, datetime

from relay.apns import DEFAULT_TTL_SECONDS, ApnsSender, PushResult
from relay.devices import PushTarget
from relay.events import NotificationEvent, alert_push
from relay.store import EventStore


class NotificationIntake:
    def __init__(self, store: EventStore, sender: ApnsSender) -> None:
        self._store = store
        self._sender = sender
        # One intake at a time, so a resend racing the first push cannot push twice.
        # The relay runs as one process with one user, so the wait stays short.
        self._lock = asyncio.Lock()

    async def receive(
        self, event: NotificationEvent, android_device_id: str, watch: PushTarget
    ) -> PushResult | None:
        """Stores `event` from the Companion and pushes it to its paired `watch`;
        None when APNs has already accepted it.

        An event whose push failed is pushed again when the Companion resends it,
        so a retry after an APNs error is never lost as a duplicate.
        Raises ApnsUnreachable when APNs cannot be reached.
        """
        async with self._lock:
            await self._store.add(event, android_device_id, datetime.now(UTC))
            if await self._store.was_pushed(event["event_id"], watch.device_id):
                return None
            result = await self._sender.send(
                watch.push_token, alert_push(event), DEFAULT_TTL_SECONDS
            )
            await self._store.record_push(
                event["event_id"], watch.device_id, result, datetime.now(UTC)
            )
            return result
