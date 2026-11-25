from aioapns import NotificationRequest
from aioapns.common import NotificationResult


class FakeApnsClient:
    """Stands in for aioapns.APNs: records the request, answers with a canned result
    or, when `error` is set, raises it."""

    def __init__(self, result: NotificationResult) -> None:
        self.result = result
        self.error: Exception | None = None
        self.requests: list[NotificationRequest] = []

    async def send_notification(self, request: NotificationRequest) -> NotificationResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result
