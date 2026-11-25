"""Replies from the watch: POST /v1/events/{event_id}/reply hands reply.execute to FCM (TZ F3)."""

import json
import sqlite3
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from relay.protocol import load_json, schema_validator
from relay.settings import SOURCE_PROTOCOL_DIR, RelaySettings
from tests.conftest import (
    EVENT,
    PAIR_COMPLETE,
    Pair,
    bearer,
    error_of,
    pair,
    post_event,
)
from tests.fakes import FakeClock, FakeFcmEndpoint

REPLY: dict[str, Any] = load_json(SOURCE_PROTOCOL_DIR / "examples" / "reply-request.json")


def post_reply(
    client: TestClient, token: str, event_id: str = EVENT["event_id"], reply: object = REPLY
) -> Response:
    """Posts a reply to the event with `token`, as the watch does."""
    return client.post(f"/v1/events/{event_id}/reply", json=reply, headers=bearer(token))


def test_reply_goes_to_the_companion_as_reply_execute(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 202
    [message] = fcm.messages
    assert message["token"] == PAIR_COMPLETE["fcm_token"]
    assert message["android"] == {"priority": "high", "ttl": "3600s"}
    data = message["data"]
    schema_validator(SOURCE_PROTOCOL_DIR, "fcm-envelope.schema.json").validate(data)
    assert {key: value for key, value in data.items() if key != "payload"} == {
        "v": "1",
        "id": REPLY["reply_id"],
        "type": "reply.execute",
        # The fake clock: when the relay sent it, not when the watch did.
        "sent_at": "2026-11-25T12:00:00Z",
        "device_id": paired.watch_device_id,
    }
    assert json.loads(data["payload"]) == {
        "reply_id": REPLY["reply_id"],
        "event_id": EVENT["event_id"],
        "notification_key": EVENT["notification_key"],
        "source_package": EVENT["source_package"],
        "text": REPLY["text"],
    }


def stored_replies(settings: RelaySettings) -> list[dict[str, Any]]:
    """The replies table, read as an operator would read it to see what happened to a reply."""
    path = settings.database_url.removeprefix("sqlite+aiosqlite:///")
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute("SELECT * FROM replies")]


def test_reply_is_kept_as_queued(client: TestClient, settings: RelaySettings, paired: Pair) -> None:
    post_event(client, paired.android_token)

    post_reply(client, paired.watch_token)

    assert stored_replies(settings) == [
        {
            "id": REPLY["reply_id"],
            "event_id": EVENT["event_id"],
            "watch_device_id": paired.watch_device_id,
            "text": REPLY["text"],
            "status": "queued",
            "error": None,
            "created_at": "2026-11-25T12:00:00Z",
            "completed_at": None,
        }
    ]


def test_reply_needs_the_watch_token(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)

    response = post_reply(client, paired.android_token)

    assert response.status_code == 401
    assert error_of(response)["code"] == "invalid_token"
    assert fcm.requests == []


def test_reply_without_text_is_refused(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)

    response = post_reply(client, paired.watch_token, reply=REPLY | {"text": ""})

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert fcm.requests == []


def test_reply_to_an_unknown_event_is_not_found(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    response = post_reply(client, paired.watch_token)

    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"
    assert fcm.requests == []


def test_reply_to_an_event_of_another_companion_looks_like_an_unknown_event(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    unknown = post_reply(
        client, paired.watch_token, event_id="7d1e0c4b-3f5a-4b6c-8d7e-9f0a1b2c3d4e"
    )
    # A new pairing: the event stays with the Companion it came from.
    repaired = pair(client)

    response = post_reply(client, repaired.watch_token)

    assert response.status_code == 404
    assert response.json() == unknown.json()
    assert fcm.requests == []


def test_reply_to_an_event_that_is_not_replyable_is_refused(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token, EVENT | {"replyable": False})

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert fcm.requests == []


def test_reply_to_an_expired_event_is_not_found(
    client: TestClient, fcm: FakeFcmEndpoint, clock: FakeClock, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    clock.advance(7 * 24 * 3600)

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"
    assert fcm.requests == []


def test_a_repeated_reply_id_is_a_duplicate_and_goes_to_fcm_once(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    post_reply(client, paired.watch_token)

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 409
    assert error_of(response)["code"] == "duplicate"
    assert len(fcm.requests) == 1
