"""APNs delivery of watch alerts: payload and headers per docs/TZ.md §5.5."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self

from aioapns import APNs, NotificationRequest, PushType
from aioapns.common import NotificationResult
from pydantic_settings import BaseSettings, SettingsConfigDict

# Notification category the watch app attaches its reply action to.
REPLY_CATEGORY = "MESSAGE_REPLY"
# apns-priority for immediate delivery (aioapns.PRIORITY_HIGH is a str, the field an int).
ALERT_PRIORITY = 10


class ApnsSettings(BaseSettings):
    """Token-based APNs credentials, read from APNS_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="APNS_")

    key_path: Path
    key_id: str
    team_id: str
    topic: str
    use_sandbox: bool = False


@dataclass(frozen=True, slots=True)
class AlertPush:
    """A user-visible notification mirrored to the watch."""

    title: str
    body: str
    source_package: str
    event_id: str
    replyable: bool

    def to_payload(self) -> dict[str, Any]:
        """APNs JSON body. Alerts from one app share a thread on the watch."""
        aps: dict[str, Any] = {
            "alert": {"title": self.title, "body": self.body},
            "sound": "default",
            "thread-id": self.source_package,
            "interruption-level": "active",
        }
        if self.replyable:
            aps["category"] = REPLY_CATEGORY
        return {
            "aps": aps,
            "event_id": self.event_id,
            "replyable": self.replyable,
            "source_package": self.source_package,
        }


@dataclass(frozen=True, slots=True)
class PushResult:
    """APNs answer to one push: the apns-id, HTTP status and rejection reason."""

    apns_id: str
    status: int
    reason: str | None

    @property
    def ok(self) -> bool:
        return self.status == 200


class ApnsClient(Protocol):
    async def send_notification(self, request: NotificationRequest) -> NotificationResult: ...


class ApnsSender:
    """Sends alert pushes over one reusable APNs connection pool."""

    def __init__(self, client: ApnsClient) -> None:
        self._client = client

    @classmethod
    def connect(cls, settings: ApnsSettings) -> Self:
        """Must run inside the event loop: aioapns binds its pool to the running loop."""
        client = APNs(
            key=settings.key_path.read_text(),
            key_id=settings.key_id,
            team_id=settings.team_id,
            topic=settings.topic,
            use_sandbox=settings.use_sandbox,
        )
        return cls(client)

    async def send(self, device_token: str, push: AlertPush, ttl: int) -> PushResult:
        """Delivers `push`; APNs keeps it for `ttl` seconds while the watch is offline."""
        request = NotificationRequest(
            device_token=device_token,
            message=push.to_payload(),
            time_to_live=ttl,
            priority=ALERT_PRIORITY,
            push_type=PushType.ALERT,
        )
        result = await self._client.send_notification(request)
        return PushResult(
            apns_id=result.notification_id,
            status=int(result.status),
            reason=result.description,
        )
