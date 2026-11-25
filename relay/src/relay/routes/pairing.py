"""Pairing and device push tokens (docs/TZ.md F1, §5.2)."""

from dataclasses import asdict

from fastapi import APIRouter, Request, Response, status

from relay.api import ApiError, CurrentDevice, CurrentRelay, parse_body
from relay.pairing import InvalidPairingCode, PairingExpired

router = APIRouter(prefix="/v1")


@router.post("/pair/start", status_code=status.HTTP_201_CREATED)
async def start_pairing(request: Request, relay: CurrentRelay) -> dict[str, str]:
    """The watch gets its device token and a code to show; the open session closes."""
    retry_after = relay.pair_start_limit.admit()
    if retry_after is not None:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many pairing starts",
            retryable=True,
            retry_after=retry_after,
        )
    body = await parse_body(request, relay.pair_start_parser)
    return asdict(await relay.pairing.start(body["apns_token"], body.get("name")))


@router.get("/pair/status")
async def pairing_status(
    pairing_id: str, relay: CurrentRelay, watch: CurrentDevice
) -> dict[str, bool]:
    """Polled by the watch while it shows the code; 404 tells it to start over."""
    try:
        return {"paired": await relay.pairing.is_paired(pairing_id, watch.id)}
    except PairingExpired as error:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "pairing_expired",
            "Pairing session is over; start a new one",
            retryable=False,
        ) from error


@router.post("/pair/complete", status_code=status.HTTP_201_CREATED)
async def complete_pairing(request: Request, relay: CurrentRelay) -> dict[str, str]:
    """The Companion enters the code the watch shows and gets its device token."""
    body = await parse_body(request, relay.pair_complete_parser)
    try:
        completed = await relay.pairing.complete(
            body["pairing_code"], body.get("fcm_token"), body.get("name")
        )
    except InvalidPairingCode as error:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_pairing_code",
            "Pairing code is wrong or no longer valid",
            retryable=False,
        ) from error
    return asdict(completed)


@router.post("/devices/{device_id}/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def update_push_token(
    device_id: str, request: Request, relay: CurrentRelay, device: CurrentDevice
) -> Response:
    """A device replaces its own APNs or FCM token; another device's id is refused."""
    if device_id != device.id:
        raise ApiError(
            status.HTTP_403_FORBIDDEN, "forbidden", "Not this token's device", retryable=False
        )
    body = await parse_body(request, relay.push_token_parser)
    await relay.devices.set_push_token(device.id, body["push_token"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
