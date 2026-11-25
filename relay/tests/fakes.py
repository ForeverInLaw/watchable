import asyncio
from datetime import datetime, timedelta

from aioapns import NotificationRequest
from aioapns.common import NotificationResult


class FakeApnsClient:
    """Stands in for aioapns.APNs: records the request, answers with a canned result
    or, when `error` is set, raises it. `delay` holds each answer back, like the network."""

    def __init__(self, result: NotificationResult) -> None:
        self.result = result
        self.error: Exception | None = None
        self.delay = 0.0
        self.requests: list[NotificationRequest] = []

    async def send_notification(self, request: NotificationRequest) -> NotificationResult:
        self.requests.append(request)
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.result


class FakeClock:
    """A clock that stands still until a test moves it."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
