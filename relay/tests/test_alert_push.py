import json

import pytest

from relay.apns import MAX_PAYLOAD_BYTES, AlertPush
from relay.events import EventParser, alert_push
from relay.settings import SOURCE_PROTOCOL_DIR
from tests.conftest import EVENT


def test_replyable_push_matches_tz_example() -> None:
    push = AlertPush(
        title="WhatsApp · Alice",
        body="Привет",
        source_package="com.whatsapp",
        event_id="018f",
        replyable=True,
    )

    assert push.to_payload() == {
        "aps": {
            "alert": {"title": "WhatsApp · Alice", "body": "Привет"},
            "sound": "default",
            "category": "MESSAGE_REPLY",
            "thread-id": "com.whatsapp",
            "interruption-level": "active",
        },
        "event_id": "018f",
        "replyable": True,
        "source_package": "com.whatsapp",
    }


def test_non_replyable_push_has_no_reply_category() -> None:
    push = AlertPush(
        title="Bank",
        body="Card charged",
        source_package="com.bank",
        event_id="018f",
        replyable=False,
    )

    payload = push.to_payload()

    assert "category" not in payload["aps"]
    assert payload["replyable"] is False


def payload_size(push: AlertPush) -> int:
    """Bytes on the wire, encoded the way aioapns sends them."""
    return len(json.dumps(push.to_payload(), ensure_ascii=False).encode())


def alert(body: str | None) -> AlertPush:
    return AlertPush(
        title="WhatsApp · Alice",
        body=body,
        source_package="com.whatsapp",
        event_id="018f3a5e-7c2b-7d4e-9a1b-3c5d7e9f1a2b",
        replyable=True,
    )


@pytest.mark.parametrize(
    "text",
    ["Пересылаю заметки 😀 ", 'quote " and\nnewline\t', "a"],
    ids=["cyrillic and emoji", "escaped characters", "ascii"],
)
def test_long_body_is_cut_to_fit_apns_limit(text: str) -> None:
    body = text * 5000
    push = alert(body)

    sent = push.to_payload()["aps"]["alert"]["body"]

    assert MAX_PAYLOAD_BYTES - 8 < payload_size(push) <= MAX_PAYLOAD_BYTES
    assert sent.endswith("…")
    assert body.startswith(sent.removesuffix("…"))


def test_body_that_fits_is_sent_whole() -> None:
    body = "a" * 3000

    assert alert(body).to_payload()["aps"]["alert"]["body"] == body


def test_alert_without_body_has_only_a_title() -> None:
    assert alert(None).to_payload()["aps"]["alert"] == {"title": "WhatsApp · Alice"}


@pytest.mark.parametrize(
    ("source_app", "sender", "title"),
    [
        ("Telegram", "Алиса", "Telegram · Алиса"),
        (None, "Алиса", "com.whatsapp · Алиса"),
        ("Telegram", None, "Telegram"),
        ("Telegram", "", "Telegram"),
    ],
    ids=["app and sender", "no app name", "no sender", "empty sender"],
)
def test_alert_title_names_app_and_sender(
    source_app: str | None, sender: str | None, title: str
) -> None:
    event = EventParser(SOURCE_PROTOCOL_DIR).parse(
        EVENT | {"source_app": source_app, "title": sender}
    )

    assert alert_push(event).title == title


def test_title_too_long_on_its_own_is_cut_too() -> None:
    push = AlertPush(
        title="Алиса " * 1000,
        body="Привет",
        source_package="com.whatsapp",
        event_id="018f3a5e-7c2b-7d4e-9a1b-3c5d7e9f1a2b",
        replyable=True,
    )

    alert_payload = push.to_payload()["aps"]["alert"]

    assert payload_size(push) <= MAX_PAYLOAD_BYTES
    assert alert_payload["title"].endswith("…")
    assert "body" not in alert_payload
