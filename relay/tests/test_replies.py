"""Replies from the watch: POST /v1/events/{event_id}/reply hands reply.execute to FCM (TZ F3)."""

import json
import sqlite3
import uuid
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from relay.protocol import load_json, schema_validator
from relay.settings import SOURCE_PROTOCOL_DIR, RelaySettings
from tests.conftest import (
    EVENT,
    PAIR_COMPLETE,
    Pair,
    bearer,
    complete_pairing,
    error_of,
    pair,
    post_event,
    start_pairing,
)
from tests.fakes import FakeClock, FakeFcmEndpoint

REPLY: dict[str, Any] = load_json(SOURCE_PROTOCOL_DIR / "examples" / "reply-request.json")
# A Companion built without Firebase pairs without an FCM token.
PAIR_COMPLETE_WITHOUT_FCM: dict[str, Any] = load_json(
    SOURCE_PROTOCOL_DIR / "examples" / "pair-complete-request.json"
)


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


def data_bytes(data: dict[str, str]) -> int:
    """What FCM counts against its 4096-byte data limit: keys and values in UTF-8."""
    return sum(len(key.encode()) + len(value.encode()) for key, value in data.items())


def test_the_longest_reply_fits_fcm_data_even_in_four_byte_characters(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    long_key = f"0|com.whatsapp|1234|{'7' * 250}@s.whatsapp.net|10001"
    post_event(client, paired.android_token, EVENT | {"notification_key": long_key})

    response = post_reply(client, paired.watch_token, reply=REPLY | {"text": "😀" * 800})

    assert response.status_code == 202
    assert data_bytes(fcm.messages[0]["data"]) <= 4096


def test_reply_over_800_characters_is_refused(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)

    response = post_reply(client, paired.watch_token, reply=REPLY | {"text": "ж" * 801})

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert fcm.requests == []


def test_reply_whose_envelope_outgrows_fcm_data_is_refused(
    client: TestClient, settings: RelaySettings, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    # Within 800 characters, but JSON escapes each control character to six bytes.
    text = "\u0001" * 800

    response = post_reply(client, paired.watch_token, reply=REPLY | {"text": text})

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert fcm.requests == []
    assert stored_replies(settings) == []


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


def fcm_error(status: int, error_code: str) -> dict[str, Any]:
    """An FCM HTTP v1 error body carrying FCM's errorCode in its details."""
    detail = {
        "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
        "errorCode": error_code,
    }
    return {"error": {"code": status, "status": error_code, "details": [detail]}}


def failure_of(settings: RelaySettings) -> tuple[str, str | None, str | None]:
    """Status, error and completed_at of the one stored reply."""
    [stored] = stored_replies(settings)
    return stored["status"], stored["error"], stored["completed_at"]


def test_reply_to_a_companion_without_an_fcm_token_fails(
    client: TestClient, settings: RelaySettings, fcm: FakeFcmEndpoint
) -> None:
    started = start_pairing(client)
    completed = complete_pairing(client, started["pairing_code"], PAIR_COMPLETE_WITHOUT_FCM).json()
    post_event(client, completed["android_device_token"])

    response = post_reply(client, started["watch_device_token"])

    assert response.status_code == 503
    assert error_of(response) | {"message": ""} == {
        "code": "fcm_token_missing",
        "message": "",
        "retryable": False,
    }
    assert failure_of(settings) == ("failed", "fcm_token_missing", "2026-11-25T12:00:00Z")
    assert fcm.requests == []


def test_an_unregistered_fcm_token_fails_the_reply_and_is_not_used_again(
    client: TestClient, settings: RelaySettings, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    fcm.status, fcm.body = 404, fcm_error(404, "UNREGISTERED")

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 503
    assert error_of(response)["code"] == "fcm_rejected"
    assert error_of(response)["retryable"] is False
    assert failure_of(settings) == ("failed", "fcm_rejected", "2026-11-25T12:00:00Z")

    another = post_reply(client, paired.watch_token, reply=REPLY | {"reply_id": str(uuid.uuid4())})

    assert error_of(another)["code"] == "fcm_token_missing"
    assert len(fcm.requests) == 1


def test_a_new_fcm_token_after_unregistered_takes_replies_again(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    fcm.status, fcm.body = 404, fcm_error(404, "UNREGISTERED")
    post_reply(client, paired.watch_token)
    client.post(
        f"/v1/devices/{paired.android_device_id}/push-token",
        json={"push_token": "new-fcm-token"},
        headers=bearer(paired.android_token),
    )
    fcm.status, fcm.body = 200, {"name": "projects/watch-app/messages/2"}

    response = post_reply(client, paired.watch_token, reply=REPLY | {"reply_id": str(uuid.uuid4())})

    assert response.status_code == 202
    assert fcm.messages[-1]["token"] == "new-fcm-token"


@pytest.mark.parametrize(
    ("status", "error_code"),
    [(429, "QUOTA_EXCEEDED"), (503, "UNAVAILABLE"), (500, "INTERNAL")],
)
def test_a_transient_fcm_error_fails_the_reply_and_may_be_retried(
    client: TestClient,
    settings: RelaySettings,
    fcm: FakeFcmEndpoint,
    paired: Pair,
    status: int,
    error_code: str,
) -> None:
    post_event(client, paired.android_token)
    fcm.status, fcm.body = status, fcm_error(status, error_code)

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 503
    assert error_of(response)["code"] == "fcm_unavailable"
    assert error_of(response)["retryable"] is True
    assert failure_of(settings) == ("failed", "fcm_unavailable", "2026-11-25T12:00:00Z")


def test_an_unreachable_fcm_fails_the_reply_and_may_be_retried(
    client: TestClient, settings: RelaySettings, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    fcm.error = httpx2.ConnectError("FCM unreachable")

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 503
    assert error_of(response)["code"] == "fcm_unavailable"
    assert error_of(response)["retryable"] is True
    assert failure_of(settings) == ("failed", "fcm_unavailable", "2026-11-25T12:00:00Z")


def test_a_reply_resent_after_a_transient_fcm_error_goes_out_again(
    client: TestClient, settings: RelaySettings, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    fcm.status, fcm.body = 503, fcm_error(503, "UNAVAILABLE")
    post_reply(client, paired.watch_token)
    fcm.status, fcm.body = 200, {"name": "projects/watch-app/messages/2"}

    response = post_reply(client, paired.watch_token)

    assert response.status_code == 202
    assert len(fcm.requests) == 2
    assert failure_of(settings) == ("queued", None, None)


def test_a_reply_resent_after_fcm_rejected_it_is_a_duplicate(
    client: TestClient, fcm: FakeFcmEndpoint, paired: Pair
) -> None:
    post_event(client, paired.android_token)
    fcm.status, fcm.body = 400, fcm_error(400, "INVALID_ARGUMENT")
    first = post_reply(client, paired.watch_token)

    response = post_reply(client, paired.watch_token)

    assert error_of(first) | {"message": ""} == {
        "code": "fcm_rejected",
        "message": "",
        "retryable": False,
    }
    assert response.status_code == 409
    assert len(fcm.requests) == 1
