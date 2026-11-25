"""The FCM HTTP v1 client: OAuth2 tokens from the service account and the message it posts."""

from typing import Any

import google.auth.exceptions
import httpx2
import pytest
from google.oauth2 import service_account

from relay.fcm import FCM_SCOPE, FcmResult, FcmSender, FcmUnreachable, ServiceAccountTokens
from tests.conftest import FCM_ACCESS_TOKEN, FCM_PROJECT_ID, fcm_sender
from tests.fakes import FakeFcmEndpoint, FakeTokenEndpoint, service_account_info

DATA = {"v": "1", "id": "4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60", "payload": "{}"}


def tokens(endpoint: FakeTokenEndpoint) -> ServiceAccountTokens:
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info(), scopes=[FCM_SCOPE]
    )
    return ServiceAccountTokens(credentials, endpoint)


async def test_access_token_is_kept_until_it_expires() -> None:
    endpoint = FakeTokenEndpoint(expires_in=3600)
    source = tokens(endpoint)

    first = await source.get()
    second = await source.get()

    assert first == second == "access-token-1"
    assert endpoint.requests == 1


async def test_expired_access_token_is_fetched_again() -> None:
    # google-auth treats a token as expired a few minutes before its expiry.
    endpoint = FakeTokenEndpoint(expires_in=60)
    source = tokens(endpoint)

    await source.get()
    second = await source.get()

    assert second == "access-token-2"
    assert endpoint.requests == 2


async def test_message_goes_to_the_project_with_the_access_token() -> None:
    fcm = FakeFcmEndpoint()

    result = await fcm_sender(fcm).send("fcm-registration-token", DATA)

    assert result == FcmResult(status=200, error=None)
    [request] = fcm.requests
    assert request.method == "POST"
    assert str(request.url) == (
        f"https://fcm.googleapis.com/v1/projects/{FCM_PROJECT_ID}/messages:send"
    )
    assert request.headers["Authorization"] == f"Bearer {FCM_ACCESS_TOKEN}"
    assert fcm.messages == [
        {
            "token": "fcm-registration-token",
            "data": DATA,
            "android": {"priority": "high", "ttl": "3600s"},
        }
    ]


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (
            {
                "error": {
                    "code": 404,
                    "status": "NOT_FOUND",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                            "errorCode": "UNREGISTERED",
                        }
                    ],
                }
            },
            "UNREGISTERED",
        ),
        ({"error": {"code": 404, "status": "NOT_FOUND"}}, "NOT_FOUND"),
        ({}, None),
    ],
    ids=["fcm error code", "status only", "no error body"],
)
async def test_rejection_reports_the_fcm_error_code(
    body: dict[str, Any], error: str | None
) -> None:
    fcm = FakeFcmEndpoint()
    fcm.status, fcm.body = 404, body

    result = await fcm_sender(fcm).send("fcm-registration-token", DATA)

    assert result == FcmResult(status=404, error=error)
    assert not result.ok


class RefusedTokens:
    """An access token source whose service account Google no longer accepts."""

    async def get(self) -> str:
        raise google.auth.exceptions.RefreshError("invalid_grant")


async def test_no_access_token_means_fcm_cannot_be_reached() -> None:
    fcm = FakeFcmEndpoint()
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(fcm))
    sender = FcmSender(http, RefusedTokens(), FCM_PROJECT_ID)

    with pytest.raises(FcmUnreachable):
        await sender.send("fcm-registration-token", DATA)
    assert fcm.requests == []


async def test_a_network_error_means_fcm_cannot_be_reached() -> None:
    fcm = FakeFcmEndpoint()
    fcm.error = httpx2.ReadTimeout("FCM did not answer")

    with pytest.raises(FcmUnreachable):
        await fcm_sender(fcm).send("fcm-registration-token", DATA)
