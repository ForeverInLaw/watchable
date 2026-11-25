from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from aioapns.common import NotificationResult
from fastapi.testclient import TestClient
from httpx2 import Response

from relay.apns import ApnsSender
from relay.app import create_app
from relay.protocol import load_json
from relay.settings import SOURCE_PROTOCOL_DIR, RelaySettings
from tests.fakes import FakeApnsClient, FakeClock

# A valid Notification event: the protocol example.
EVENT: dict[str, Any] = load_json(SOURCE_PROTOCOL_DIR / "examples" / "notification-event.json")
PAIR_START: dict[str, Any] = load_json(SOURCE_PROTOCOL_DIR / "examples" / "pair-start-request.json")
PAIR_COMPLETE: dict[str, Any] = load_json(
    SOURCE_PROTOCOL_DIR / "examples" / "pair-complete-request.json"
)
# Where the fake clock starts.
START = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def apns() -> FakeApnsClient:
    return FakeApnsClient(NotificationResult("apns-1", "200"))


@pytest.fixture
def settings(tmp_path: Path) -> RelaySettings:
    return RelaySettings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'relay.db'}")


@pytest.fixture
def client(settings: RelaySettings, apns: FakeApnsClient, clock: FakeClock) -> Iterator[TestClient]:
    app = create_app(settings, connect_apns=lambda: ApnsSender(apns), clock=clock)
    with TestClient(app) as test_client:
        yield test_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True, slots=True)
class Pair:
    """Ids and tokens of a watch and a Companion paired through the API."""

    pairing_id: str
    watch_device_id: str
    watch_token: str
    android_device_id: str
    android_token: str


def start_pairing(client: TestClient, apns_token: str = PAIR_START["apns_token"]) -> dict[str, Any]:
    """The pair-start-response body for a watch with `apns_token`."""
    response = client.post("/v1/pair/start", json=PAIR_START | {"apns_token": apns_token})
    assert response.status_code == 201
    started: dict[str, Any] = response.json()
    return started


def complete_pairing(client: TestClient, code: str) -> Response:
    return client.post("/v1/pair/complete", json=PAIR_COMPLETE | {"pairing_code": code})


def pair(client: TestClient, apns_token: str = PAIR_START["apns_token"]) -> Pair:
    started = start_pairing(client, apns_token)
    response = complete_pairing(client, started["pairing_code"])
    assert response.status_code == 201
    completed = response.json()
    return Pair(
        pairing_id=started["pairing_id"],
        watch_device_id=started["watch_device_id"],
        watch_token=started["watch_device_token"],
        android_device_id=completed["android_device_id"],
        android_token=completed["android_device_token"],
    )


@pytest.fixture
def paired(client: TestClient) -> Pair:
    return pair(client)
