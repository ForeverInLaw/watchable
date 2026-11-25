"""The relay HTTP API, driven through FastAPI with APNs faked and a fresh SQLite file."""

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from aioapns.common import NotificationResult
from aioapns.exceptions import MaxAttemptsExceeded
from fastapi.testclient import TestClient
from httpx2 import Headers

from relay.apns import ApnsSender
from relay.app import create_app
from relay.settings import RelaySettings
from tests.conftest import EVENT, PAIR_START, Pair, bearer, error_of, post_event
from tests.fakes import FakeApnsClient


def test_healthz_reports_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_event_is_pushed_to_the_watch(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    response = post_event(client, paired.android_token)

    assert response.status_code == 202
    [request] = apns.requests
    assert request.device_token == PAIR_START["apns_token"]
    assert request.message["aps"]["alert"] == {"title": "WhatsApp · Alice", "body": "Привет"}
    assert request.message["event_id"] == EVENT["event_id"]


def test_resent_event_is_not_pushed_twice(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    post_event(client, paired.android_token)

    response = post_event(client, paired.android_token)

    assert response.status_code == 409
    assert error_of(response) == {
        "code": "duplicate",
        "message": "Event already delivered",
        "retryable": False,
    }
    assert len(apns.requests) == 1


def test_event_apns_failed_to_take_is_pushed_on_resend(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    apns.result = NotificationResult("apns-1", "503", "ServiceUnavailable")
    failed = post_event(client, paired.android_token)
    apns.result = NotificationResult("apns-2", "200")

    resent = post_event(client, paired.android_token)

    assert failed.status_code == 503
    assert error_of(failed)["retryable"] is True
    assert resent.status_code == 202
    assert len(apns.requests) == 2


def test_push_apns_rejects_is_not_retryable(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    apns.result = NotificationResult("apns-1", "400", "BadDeviceToken")

    response = post_event(client, paired.android_token)

    assert response.status_code == 500
    assert error_of(response) == {
        "code": "apns_rejected",
        "message": "APNs rejected the push: BadDeviceToken",
        "retryable": False,
    }


def test_unreachable_apns_is_retryable(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    apns.error = MaxAttemptsExceeded()

    response = post_event(client, paired.android_token)

    assert response.status_code == 503
    assert error_of(response) == {
        "code": "apns_unavailable",
        "message": "APNs unreachable",
        "retryable": True,
    }


@pytest.mark.parametrize(
    "headers_of",
    [
        lambda _: {},
        lambda _: bearer("wrong"),
        lambda pair: {"Authorization": pair.android_token},
        lambda pair: bearer(pair.watch_token),
    ],
    ids=["no header", "wrong token", "no bearer scheme", "watch token"],
)
def test_event_without_the_companion_token_is_refused(
    client: TestClient,
    apns: FakeApnsClient,
    paired: Pair,
    headers_of: Callable[[Pair], dict[str, str]],
) -> None:
    response = client.post("/v1/events/notification", json=EVENT, headers=headers_of(paired))

    assert response.status_code == 401
    assert error_of(response)["code"] == "invalid_token"
    assert apns.requests == []


@pytest.mark.parametrize(
    "event",
    [
        EVENT | {"posted_at": "2026-11-24T15:00:00+03:00"},
        {name: value for name, value in EVENT.items() if name != "notification_key"},
        EVENT | {"body_truncated": False},
        EVENT | {"replyable": "yes"},
        [EVENT],
    ],
    ids=["posted_at not in UTC", "no notification_key", "unknown field", "wrong type", "array"],
)
def test_event_breaking_the_schema_is_refused(
    client: TestClient, apns: FakeApnsClient, event: object, paired: Pair
) -> None:
    response = post_event(client, paired.android_token, event)

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert error_of(response)["retryable"] is False
    assert apns.requests == []


def test_error_names_the_rule_not_the_value(client: TestClient, paired: Pair) -> None:
    response = post_event(client, paired.android_token, EVENT | {"event_id": "secret-text"})

    assert error_of(response)["message"] == "$.event_id fails format"


@pytest.mark.parametrize("content", [b"{not json", b'{"title": "\xff"}'], ids=["json", "utf-8"])
def test_body_that_is_not_json_is_refused(client: TestClient, content: bytes, paired: Pair) -> None:
    response = client.post(
        "/v1/events/notification",
        content=content,
        headers=bearer(paired.android_token) | {"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"


def test_token_that_is_not_ascii_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/events/notification", json=EVENT, headers=Headers([(b"Authorization", b"Bearer \xff")])
    )

    assert response.status_code == 401
    assert error_of(response)["code"] == "invalid_token"


def test_unknown_path_answers_in_the_error_shape(client: TestClient) -> None:
    response = client.get("/v1/nowhere")

    assert response.status_code == 404
    assert error_of(response) == {"code": "not_found", "message": "Not Found", "retryable": False}


def test_unexpected_failure_is_retryable(
    settings: RelaySettings, apns: FakeApnsClient, paired: Pair
) -> None:
    apns.error = RuntimeError("boom")
    app = create_app(settings, connect_apns=lambda: ApnsSender(apns))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = post_event(client, paired.android_token)

    assert response.status_code == 500
    assert error_of(response) == {
        "code": "internal_error",
        "message": "Internal Server Error",
        "retryable": True,
    }


def test_delivered_event_stays_delivered_after_restart(
    settings: RelaySettings, apns: FakeApnsClient, paired: Pair
) -> None:
    for expected in (202, 409):
        app = create_app(settings, connect_apns=lambda: ApnsSender(apns))
        with TestClient(app) as client:
            assert post_event(client, paired.android_token).status_code == expected

    assert len(apns.requests) == 1


def test_resend_racing_the_first_push_is_not_pushed(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    apns.delay = 0.2

    with ThreadPoolExecutor() as pool:
        responses = list(pool.map(lambda _: post_event(client, paired.android_token), range(2)))

    assert sorted(response.status_code for response in responses) == [202, 409]
    assert len(apns.requests) == 1


def test_body_over_32_kb_is_refused(client: TestClient, apns: FakeApnsClient, paired: Pair) -> None:
    response = post_event(client, paired.android_token, EVENT | {"body": "a" * 32 * 1024})

    assert response.status_code == 413
    assert error_of(response) == {
        "code": "payload_too_large",
        "message": "Body over 32768 bytes",
        "retryable": False,
    }
    assert apns.requests == []


def test_text_that_is_not_valid_unicode_is_refused(
    client: TestClient, apns: FakeApnsClient, paired: Pair
) -> None:
    # A lone surrogate is valid JSON (an escape) but cannot be stored or sent as UTF-8.
    content = json.dumps(EVENT | {"title": "\ud800"}).encode()

    response = client.post(
        "/v1/events/notification",
        content=content,
        headers=bearer(paired.android_token) | {"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert apns.requests == []
