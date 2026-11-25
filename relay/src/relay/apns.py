"""APNs delivery of watch alerts: payload and headers per docs/TZ.md §5.5."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self

from aioapns import APNs, NotificationRequest, PushType
from aioapns.common import NotificationResult
from aioapns.exceptions import MaxAttemptsExceeded
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
        """APNs JSON body, cut to fit MAX_PAYLOAD_BYTES (TZ §5.5).

        The body is cut first. A title too long to fit even with an empty body is cut
        as well, and the body is dropped. Alerts from one app share a thread on the watch.
        """
        payload = self._payload(self.title, self.body)
        if payload_size(payload) <= MAX_PAYLOAD_BYTES:
            return payload
        if self.body is not None:
            body = cut_to_fit(self.body, lambda body: self._payload(self.title, body))
            if body is not None:
                return self._payload(self.title, body)
        title = cut_to_fit(self.title, lambda title: self._payload(title, None))
        # None only when source_package alone overflows; APNs then refuses the push.
        return self._payload(title or ELLIPSIS, None)

    def _payload(self, title: str, body: str | None) -> dict[str, Any]:
        alert = {"title": title}
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


def cut_to_fit(text: str, build: Callable[[str], dict[str, Any]]) -> str | None:
    """The longest prefix of `text`, ending in the ellipsis, whose payload fits.

    None when even the ellipsis alone does not fit. JSON escapes make the size uneven
    per character, so this searches over code points rather than computes.
    """
    if payload_size(build(ELLIPSIS)) > MAX_PAYLOAD_BYTES:
        return None
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if payload_size(build(text[:middle] + ELLIPSIS)) <= MAX_PAYLOAD_BYTES:
            low = middle
        else:
            high = middle - 1
    return text[:low] + ELLIPSIS


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

    @property
    def retryable(self) -> bool:
        """Throttling and APNs outages pass; a rejected token or payload does not."""
        return self.status == 429 or self.status >= 500


class ApnsUnreachable(Exception):
    """aioapns ran out of connection attempts; the push was not delivered."""


def join_token_groups(token: str) -> str:
    """The device token without the spaces the watch app shows between its groups."""
    return "".join(token.split())


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
        try:
            result = await self._client.send_notification(request)
        except MaxAttemptsExceeded as error:
            raise ApnsUnreachable from error
        return PushResult(
            apns_id=result.notification_id,
            status=int(result.status),
            reason=result.description,
        )
