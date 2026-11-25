"""The FCM HTTP v1 client: OAuth2 tokens from the service account and the message it posts."""

import json

import httpx2
import pytest
from google.oauth2 import service_account

from relay.fcm import FCM_SCOPE, FcmResult, FcmSender, ServiceAccountTokens
from tests.fakes import FakeTokenEndpoint, FakeTokens, service_account_info

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


def sender(handler: httpx2.MockTransport) -> FcmSender:
    return FcmSender(httpx2.AsyncClient(transport=handler), FakeTokens("ya29.token"), "watch-app")


async def test_message_goes_to_the_project_with_the_access_token() -> None:
    requests: list[httpx2.Request] = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"name": "projects/watch-app/messages/1"})

    result = await sender(httpx2.MockTransport(answer)).send("fcm-registration-token", DATA)

    assert result == FcmResult(status=200, error=None)
    [request] = requests
    assert request.method == "POST"
    assert str(request.url) == "https://fcm.googleapis.com/v1/projects/watch-app/messages:send"
    assert request.headers["Authorization"] == "Bearer ya29.token"
    assert json.loads(request.content) == {
        "message": {
            "token": "fcm-registration-token",
            "data": DATA,
            "android": {"priority": "high", "ttl": "3600s"},
        }
    }


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
async def test_rejection_reports_the_fcm_error_code(body: object, error: str | None) -> None:
    transport = httpx2.MockTransport(lambda _request: httpx2.Response(404, json=body))

    result = await sender(transport).send("fcm-registration-token", DATA)

    assert result == FcmResult(status=404, error=error)
    assert not result.ok
