from aioapns import NotificationRequest
from aioapns.common import NotificationResult


class FakeApnsClient:
    """Stands in for aioapns.APNs: records the request, answers with a canned result."""

    def __init__(self, result: NotificationResult) -> None:
        self.result = result
        self.requests: list[NotificationRequest] = []

    async def send_notification(self, request: NotificationRequest) -> NotificationResult:
        self.requests.append(request)
        return self.result
