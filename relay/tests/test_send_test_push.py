import os
from pathlib import Path

import pytest
from aioapns import NotificationRequest
from aioapns.common import NotificationResult
from aioapns.exceptions import MaxAttemptsExceeded

from relay.apns import ApnsSender, ApnsSettings
from relay.send_test_push import main
from tests.fakes import FakeApnsClient

TOKEN = "a1b2"


@pytest.fixture(autouse=True)
def apns_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "AuthKey_ENV.p8"
    key.write_text("not a real key: the fake client never signs")
    monkeypatch.setenv("APNS_KEY_PATH", str(key))
    monkeypatch.setenv("APNS_KEY_ID", "ENVKEY")
    monkeypatch.setenv("APNS_TEAM_ID", "ENVTEAM")
    monkeypatch.setenv("APNS_TOPIC", "env.topic")
    monkeypatch.delenv("APNS_USE_SANDBOX", raising=False)


class Connector:
    """Replaces ApnsSender.connect: keeps the settings, sends through a fake client."""

    def __init__(self, status: str = "200", reason: str | None = None) -> None:
        self.client = FakeApnsClient(NotificationResult("abc", status, reason))
        self.settings: ApnsSettings | None = None

    def __call__(self, settings: ApnsSettings) -> ApnsSender:
        self.settings = settings
        return ApnsSender(self.client)


def test_arguments_override_env_and_production_is_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    connect = Connector()

    code = main([TOKEN, "--key-id", "ARGKEY"], connect=connect)

    assert code == 0
    assert connect.settings is not None
    assert connect.settings.key_id == "ARGKEY"
    assert connect.settings.team_id == "ENVTEAM"
    assert connect.settings.use_sandbox is False
    [request] = connect.client.requests
    assert request.device_token == TOKEN
    assert request.time_to_live == 3600
    assert "apns-id: abc" in capsys.readouterr().out


def test_sandbox_flag_selects_development_environment() -> None:
    connect = Connector()

    main([TOKEN, "--sandbox"], connect=connect)

    assert connect.settings is not None
    assert connect.settings.use_sandbox is True


def test_rejected_push_prints_reason_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([TOKEN], connect=Connector(status="400", reason="BadDeviceToken"))

    assert code == 1
    out = capsys.readouterr().out
    assert "status:  400" in out
    assert "reason:  BadDeviceToken" in out


def test_missing_credential_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("APNS_TEAM_ID")

    with pytest.raises(SystemExit) as exit_info:
        main([TOKEN], connect=Connector())

    assert exit_info.value.code == 2
    assert "APNS_TEAM_ID" in capsys.readouterr().err


def test_missing_key_file_names_the_variable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([TOKEN, "--key-path", str(tmp_path / "absent.p8")], connect=Connector())

    assert exit_info.value.code == 2
    assert "APNS_KEY_PATH" in capsys.readouterr().err


class UnreachableClient:
    """Behaves like aioapns.APNs after it has run out of connection attempts."""

    async def send_notification(self, request: NotificationRequest) -> NotificationResult:
        raise MaxAttemptsExceeded


def test_unreachable_apns_fails_with_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([TOKEN], connect=lambda _settings: ApnsSender(UnreachableClient()))

    assert exit_info.value.code == 1
    assert "APNs unreachable" in capsys.readouterr().err


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads files regardless of mode")
def test_unreadable_key_file_names_the_variable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    key = tmp_path / "locked.p8"
    key.write_text("key")
    key.chmod(0)

    with pytest.raises(SystemExit) as exit_info:
        main([TOKEN, "--key-path", str(key)], connect=Connector())

    assert exit_info.value.code == 2
    assert "APNS_KEY_PATH" in capsys.readouterr().err
