"""Notification intake: POST /v1/events/notification (docs/TZ.md §5.4)."""

from fastapi import APIRouter, Request, Response, status

from relay.api import ApiError, CurrentAndroid, CurrentRelay, invalid_token, parse_body
from relay.apns import ApnsUnreachable

router = APIRouter()


@router.post("/v1/events/notification", status_code=status.HTTP_202_ACCEPTED)
async def receive_notification(
    request: Request, relay: CurrentRelay, android: CurrentAndroid
) -> Response:
    """Stores the event and pushes it to the paired watch; 202 once APNs accepts the push."""
    event = await parse_body(request, relay.event_parser)
    watch = await relay.devices.paired_watch(android.id)
    if watch is None:
        raise invalid_token()

    try:
        result = await relay.intake.receive(event, android.id, watch)
    except ApnsUnreachable as error:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "apns_unavailable",
            "APNs unreachable",
            retryable=True,
        ) from error

    if result is None:
        raise ApiError(
            status.HTTP_409_CONFLICT, "duplicate", "Event already delivered", retryable=False
        )
    if not result.ok:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE
            if result.retryable
            else status.HTTP_500_INTERNAL_SERVER_ERROR,
            "apns_rejected",
            f"APNs rejected the push: {result.reason or result.status}",
            retryable=result.retryable,
        )
    return Response(status_code=status.HTTP_202_ACCEPTED)
