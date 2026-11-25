"""Pairing over the relay HTTP API (docs/TZ.md F1, §5.2), with the clock and APNs faked."""

from typing import Any

from fastapi.testclient import TestClient

from relay.protocol import schema_validator
from relay.settings import SOURCE_PROTOCOL_DIR
from tests.conftest import (
    EVENT,
    PAIR_START,
    Pair,
    bearer,
    complete_pairing,
    pair,
    start_pairing,
)
from tests.fakes import FakeApnsClient, FakeClock


def body_of(response: Any, schema: str) -> dict[str, Any]:
    """The JSON body of `response`, checked against protocol/schema/<schema>.schema.json."""
    body: dict[str, Any] = response.json()
    schema_validator(SOURCE_PROTOCOL_DIR, f"{schema}.schema.json").validate(body)
    return body


def test_start_gives_the_watch_a_code_for_ten_minutes(client: TestClient) -> None:
    response = client.post("/v1/pair/start", json=PAIR_START)

    assert response.status_code == 201
    started = body_of(response, "pair-start-response")
    assert started["expires_at"] == "2026-11-25T12:10:00Z"


def pair_status(client: TestClient, pairing_id: str, watch_token: str) -> Any:
    return client.get(
        "/v1/pair/status", params={"pairing_id": pairing_id}, headers=bearer(watch_token)
    )


def test_watch_learns_the_companion_entered_its_code(client: TestClient) -> None:
    started = start_pairing(client)
    pairing_id, watch_token = started["pairing_id"], started["watch_device_token"]
    waiting = pair_status(client, pairing_id, watch_token)

    completed = complete_pairing(client, started["pairing_code"])

    assert body_of(waiting, "pair-status-response") == {"paired": False}
    assert completed.status_code == 201
    assert (
        body_of(completed, "pair-complete-response")["watch_device_id"]
        == (started["watch_device_id"])
    )
    assert body_of(pair_status(client, pairing_id, watch_token), "pair-status-response") == {
        "paired": True
    }


def error_code(response: Any) -> str:
    code: str = body_of(response, "error")["error"]["code"]
    return code


def wrong_code(code: str) -> str:
    """Another 8-digit code than `code`."""
    return f"{(int(code) + 1) % 10**8:08d}"


def test_code_works_only_once(client: TestClient) -> None:
    started = start_pairing(client)
    complete_pairing(client, started["pairing_code"])

    again = complete_pairing(client, started["pairing_code"])

    assert again.status_code == 400
    assert error_code(again) == "invalid_pairing_code"


def test_four_wrong_codes_leave_the_session_open(client: TestClient) -> None:
    started = start_pairing(client)
    for _ in range(4):
        assert complete_pairing(client, wrong_code(started["pairing_code"])).status_code == 400

    assert complete_pairing(client, started["pairing_code"]).status_code == 201


def test_fifth_wrong_code_burns_the_session(client: TestClient) -> None:
    started = start_pairing(client)
    for _ in range(5):
        wrong = complete_pairing(client, wrong_code(started["pairing_code"]))
        assert error_code(wrong) == "invalid_pairing_code"

    right = complete_pairing(client, started["pairing_code"])
    status = pair_status(client, started["pairing_id"], started["watch_device_token"])

    assert right.status_code == 400
    assert error_code(right) == "invalid_pairing_code"
    assert status.status_code == 404
    assert error_code(status) == "pairing_expired"


def test_code_expires_after_ten_minutes(client: TestClient, clock: FakeClock) -> None:
    started = start_pairing(client)
    clock.advance(10 * 60)

    late = complete_pairing(client, started["pairing_code"])
    status = pair_status(client, started["pairing_id"], started["watch_device_token"])

    assert error_code(late) == "invalid_pairing_code"
    assert error_code(status) == "pairing_expired"


def test_new_start_replaces_the_open_session(client: TestClient) -> None:
    first = start_pairing(client)
    second = start_pairing(client)

    old_code = complete_pairing(client, first["pairing_code"])
    old_status = pair_status(client, first["pairing_id"], first["watch_device_token"])

    assert error_code(old_code) == "invalid_pairing_code"
    assert error_code(old_status) == "pairing_expired"
    assert complete_pairing(client, second["pairing_code"]).status_code == 201


def post_event(client: TestClient, token: str, event_id: str) -> Any:
    return client.post(
        "/v1/events/notification", json=EVENT | {"event_id": event_id}, headers=bearer(token)
    )


def test_start_leaves_the_current_pair_working(client: TestClient, paired: Pair) -> None:
    start_pairing(client, apns_token="ffff")

    response = post_event(client, paired.android_token, "11111111-1111-4111-8111-111111111111")

    assert response.status_code == 202


def test_repair_revokes_the_old_devices(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    repaired = pair(client, apns_token="ffff")

    old_android = post_event(client, paired.android_token, "11111111-1111-4111-8111-111111111111")
    old_watch = pair_status(client, paired.pairing_id, paired.watch_token)
    new_android = post_event(client, repaired.android_token, "22222222-2222-4222-8222-222222222222")

    assert error_code(old_android) == "invalid_token"
    assert error_code(old_watch) == "invalid_token"
    assert new_android.status_code == 202
    assert [request.device_token for request in apns.requests] == ["ffff"]


def test_watch_pushes_go_to_its_new_apns_token(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    updated = client.post(
        f"/v1/devices/{paired.watch_device_id}/push-token",
        json={"push_token": "abcdef"},
        headers=bearer(paired.watch_token),
    )
    post_event(client, paired.android_token, "11111111-1111-4111-8111-111111111111")

    assert updated.status_code == 204
    assert [request.device_token for request in apns.requests] == ["abcdef"]


def test_device_cannot_set_another_devices_push_token(client: TestClient, paired: Pair) -> None:
    response = client.post(
        f"/v1/devices/{paired.watch_device_id}/push-token",
        json={"push_token": "abcdef"},
        headers=bearer(paired.android_token),
    )

    assert response.status_code == 403
    assert error_code(response) == "forbidden"


def test_eleventh_start_in_a_minute_is_rate_limited(client: TestClient, clock: FakeClock) -> None:
    for _ in range(10):
        start_pairing(client)
        clock.advance(1)

    limited = client.post("/v1/pair/start", json=PAIR_START)
    clock.advance(50)
    later = client.post("/v1/pair/start", json=PAIR_START)

    assert limited.status_code == 429
    assert error_code(limited) == "rate_limited"
    assert body_of(limited, "error")["error"]["retryable"] is True
    assert limited.headers["Retry-After"] == "50"
    assert later.status_code == 201


def test_status_without_a_pairing_id_is_invalid(client: TestClient) -> None:
    started = start_pairing(client)

    response = client.get("/v1/pair/status", headers=bearer(started["watch_device_token"]))

    assert response.status_code == 400
    assert body_of(response, "error")["error"] == {
        "code": "invalid_request",
        "message": "Invalid request parameters",
        "retryable": False,
    }
