from aioapns import PushType
from aioapns.common import NotificationResult

from relay.apns import AlertPush, ApnsSender, PushResult
from tests.fakes import FakeApnsClient

PUSH = AlertPush(
    title="Test",
    body="Hello",
    source_package="relay.test",
    event_id="018f",
    replyable=False,
)


async def test_sends_high_priority_alert_with_ttl() -> None:
    client = FakeApnsClient(NotificationResult("abc", "200"))

    await ApnsSender(client).send("a1b2", PUSH, ttl=3600)

    [request] = client.requests
    assert request.device_token == "a1b2"
    assert request.message == PUSH.to_payload()
    assert request.push_type is PushType.ALERT
    assert str(request.priority) == "10"  # apns-priority header value
    assert request.time_to_live == 3600


async def test_reports_apns_rejection() -> None:
    client = FakeApnsClient(NotificationResult("abc", "400", "BadDeviceToken"))

    result = await ApnsSender(client).send("a1b2", PUSH, ttl=0)

    assert result == PushResult(apns_id="abc", status=400, reason="BadDeviceToken")
    assert not result.ok
