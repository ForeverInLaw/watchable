from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from aioapns.common import NotificationResult
from fastapi.testclient import TestClient

from relay.apns import ApnsSender
from relay.app import create_app
from relay.protocol import load_json
from relay.settings import SOURCE_PROTOCOL_DIR, RelaySettings
from tests.fakes import FakeApnsClient

TOKEN = "companion-secret"
WATCH_PUSH_TOKEN = "a1b2c3d4"
# A valid Notification event: the protocol example.
EVENT: dict[str, Any] = load_json(SOURCE_PROTOCOL_DIR / "examples" / "notification-event.json")


@pytest.fixture
def apns() -> FakeApnsClient:
    return FakeApnsClient(NotificationResult("apns-1", "200"))


@pytest.fixture
def settings(tmp_path: Path) -> RelaySettings:
    return RelaySettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'relay.db'}",
        relay_token=TOKEN,
        # Grouped as the watch app shows it; pushes go to WATCH_PUSH_TOKEN.
        watch_push_token="a1b2 c3d4",
    )


@pytest.fixture
def client(settings: RelaySettings, apns: FakeApnsClient) -> Iterator[TestClient]:
    app = create_app(settings, connect_apns=lambda: ApnsSender(apns))
    with TestClient(app) as test_client:
        yield test_client
