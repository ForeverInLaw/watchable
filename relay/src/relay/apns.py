"""APNs delivery of watch alerts: payload and headers per docs/TZ.md §5.5."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self

from aioapns import APNs, NotificationRequest, PushType
from aioapns.common import NotificationResult
from pydantic import FilePath, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Notification category the watch app attaches its reply action to.
REPLY_CATEGORY = "MESSAGE_REPLY"
# apns-priority for immediate delivery (aioapns.PRIORITY_HIGH is a str, the field an int).
ALERT_PRIORITY = 10
# Seconds APNs keeps a push while the watch is offline (TZ §5.5).
DEFAULT_TTL_SECONDS = 3600
# APNs refuses a larger alert payload with PayloadTooLarge.
MAX_PAYLOAD_BYTES = 4096
# Ends an alert body cut to fit; the full text stays on the relay.
ELLIPSIS = "…"


class ApnsSettings(BaseSettings):
    """Token-based APNs credentials, read from APNS_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="APNS_")

    key_path: FilePath
    key_id: str
    team_id: str
    topic: str
    use_sandbox: bool = False

    @field_validator("key_path")
    @classmethod
    def key_is_readable(cls, path: Path) -> Path:
        """Rejects an unreadable key here, so it fails like any other bad setting."""
        try:
            path.read_bytes()
        except OSError as error:
            raise ValueError(f"cannot read the key: {error.strerror}") from error
        return path


@dataclass(frozen=True, slots=True)
class AlertPush:
    """A user-visible notification mirrored to the watch."""

    title: str
    body: str | None
    source_package: str
    event_id: str
    replyable: bool

    def to_payload(self) -> dict[str, Any]:
        """APNs JSON body, its alert body cut to fit MAX_PAYLOAD_BYTES (TZ §5.5).

        Alerts from one app share a thread on the watch.
        """
        payload = self._payload(self.body)
        if self.body is None or payload_size(payload) <= MAX_PAYLOAD_BYTES:
            return payload
        # The longest prefix of the body that fits with the ellipsis, in code points.
        # JSON escapes make the size uneven per character, so search rather than compute.
        low, high = 0, len(self.body)
        while low < high:
            middle = (low + high + 1) // 2
            if payload_size(self._payload(self.body[:middle] + ELLIPSIS)) <= MAX_PAYLOAD_BYTES:
                low = middle
            else:
                high = middle - 1
        return self._payload(self.body[:low] + ELLIPSIS)

    def _payload(self, body: str | None) -> dict[str, Any]:
        alert = {"title": self.title}
        if body is not None:
            alert["body"] = body
        aps: dict[str, Any] = {
            "alert": alert,
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


def payload_size(payload: dict[str, Any]) -> int:
    """Bytes APNs counts: aioapns sends json.dumps(payload, ensure_ascii=False) as UTF-8."""
    return len(json.dumps(payload, ensure_ascii=False).encode())


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
