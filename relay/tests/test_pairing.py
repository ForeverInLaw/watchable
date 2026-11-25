"""Pairing over the relay HTTP API (docs/TZ.md F1, §5.2), with the clock and APNs faked."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    PAIR_START,
    PAIRING_SECRET,
    Pair,
    bearer,
    body_of,
    complete_pairing,
    error_of,
    pair,
    post_event,
    start_pairing,
)
from tests.fakes import FakeApnsClient, FakeClock


def test_start_gives_the_watch_a_code_for_ten_minutes(client: TestClient) -> None:
    response = client.post("/v1/pair/start", json=PAIR_START, headers=bearer(PAIRING_SECRET))

    assert response.status_code == 201
    started = body_of(response, "pair-start-response")
    assert started["expires_at"] == "2026-11-25T12:10:00Z"


def pair_status(client: TestClient, pairing_id: str, watch_token: str) -> Any:
    return client.get(
        "/v1/pair/status", params={"pairing_id": pairing_id}, headers=bearer(watch_token)
    )


@pytest.mark.parametrize(
    "headers",
    [{}, bearer("wrong-secret"), {"Authorization": PAIRING_SECRET}],
    ids=["no header", "wrong secret", "no bearer scheme"],
)
def test_start_without_the_pairing_secret_is_refused(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post("/v1/pair/start", json=PAIR_START, headers=headers)

    assert response.status_code == 401
    assert error_of(response) == {
        "code": "invalid_pairing_secret",
        "message": "Pairing secret required",
        "retryable": False,
    }


def test_refused_starts_do_not_use_up_the_rate_limit(client: TestClient) -> None:
    for _ in range(20):
        client.post("/v1/pair/start", json=PAIR_START, headers=bearer("wrong-secret"))

    response = client.post("/v1/pair/start", json=PAIR_START, headers=bearer(PAIRING_SECRET))

    assert response.status_code == 201


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


def wrong_code(code: str) -> str:
    """Another 8-digit code than `code`."""
    return f"{(int(code) + 1) % 10**8:08d}"


def test_code_works_only_once(client: TestClient) -> None:
    started = start_pairing(client)
    complete_pairing(client, started["pairing_code"])

    again = complete_pairing(client, started["pairing_code"])

    assert again.status_code == 400
    assert error_of(again)["code"] == "invalid_pairing_code"


def test_four_wrong_codes_leave_the_session_open(client: TestClient) -> None:
    started = start_pairing(client)
    for _ in range(4):
        assert complete_pairing(client, wrong_code(started["pairing_code"])).status_code == 400

    assert complete_pairing(client, started["pairing_code"]).status_code == 201


def test_fifth_wrong_code_burns_the_session(client: TestClient) -> None:
    started = start_pairing(client)
    for _ in range(5):
        wrong = complete_pairing(client, wrong_code(started["pairing_code"]))
        assert error_of(wrong)["code"] == "invalid_pairing_code"

    right = complete_pairing(client, started["pairing_code"])
    status = pair_status(client, started["pairing_id"], started["watch_device_token"])

    assert right.status_code == 400
    assert error_of(right)["code"] == "invalid_pairing_code"
    assert status.status_code == 404
    assert error_of(status)["code"] == "pairing_expired"


def test_code_expires_after_ten_minutes(client: TestClient, clock: FakeClock) -> None:
    started = start_pairing(client)
    clock.advance(10 * 60)

    late = complete_pairing(client, started["pairing_code"])
    status = pair_status(client, started["pairing_id"], started["watch_device_token"])

    assert error_of(late)["code"] == "invalid_pairing_code"
    assert error_of(status)["code"] == "pairing_expired"


def test_new_start_replaces_the_open_session(client: TestClient) -> None:
    first = start_pairing(client)
    second = start_pairing(client)

    old_code = complete_pairing(client, first["pairing_code"])
    old_status = pair_status(client, first["pairing_id"], first["watch_device_token"])

    assert error_of(old_code)["code"] == "invalid_pairing_code"
    assert error_of(old_status)["code"] == "pairing_expired"
    assert complete_pairing(client, second["pairing_code"]).status_code == 201


def test_start_leaves_the_current_pair_working(client: TestClient, paired: Pair) -> None:
    start_pairing(client, apns_token="ffff")

    response = post_event(client, paired.android_token)

    assert response.status_code == 202


def test_repair_revokes_the_old_devices(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    repaired = pair(client, apns_token="ffff")

    old_android = post_event(client, paired.android_token)
    old_watch = pair_status(client, paired.pairing_id, paired.watch_token)
    new_android = post_event(client, repaired.android_token)

    assert error_of(old_android)["code"] == "invalid_token"
    assert error_of(old_watch)["code"] == "invalid_token"
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
    post_event(client, paired.android_token)

    assert updated.status_code == 204
    assert [request.device_token for request in apns.requests] == ["abcdef"]


def test_device_cannot_set_another_devices_push_token(client: TestClient, paired: Pair) -> None:
    response = client.post(
        f"/v1/devices/{paired.watch_device_id}/push-token",
        json={"push_token": "abcdef"},
        headers=bearer(paired.android_token),
    )

    assert response.status_code == 403
    assert error_of(response)["code"] == "forbidden"


def test_eleventh_start_in_a_minute_is_rate_limited(client: TestClient, clock: FakeClock) -> None:
    for _ in range(10):
        start_pairing(client)
        clock.advance(1)

    limited = client.post("/v1/pair/start", json=PAIR_START, headers=bearer(PAIRING_SECRET))
    clock.advance(50)
    later = client.post("/v1/pair/start", json=PAIR_START, headers=bearer(PAIRING_SECRET))

    assert limited.status_code == 429
    assert error_of(limited) == {
        "code": "rate_limited",
        "message": "Too many pairing starts",
        "retryable": True,
    }
    assert limited.headers["Retry-After"] == "50"
    assert later.status_code == 201


def test_status_without_a_pairing_id_is_invalid(client: TestClient) -> None:
    started = start_pairing(client)

    response = client.get("/v1/pair/status", headers=bearer(started["watch_device_token"]))

    assert response.status_code == 400
    assert error_of(response) == {
        "code": "invalid_request",
        "message": "Invalid request parameters",
        "retryable": False,
    }
