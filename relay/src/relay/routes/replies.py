"""Replies from the watch: POST /v1/events/{event_id}/reply (docs/TZ.md F3, §5.6)."""

from fastapi import APIRouter, Request, Response, status

from relay.api import ApiError, CurrentRelay, CurrentWatch, invalid_token, parse_body
from relay.replies import NoCompanion, UnknownEvent

router = APIRouter()


@router.post("/v1/events/{event_id}/reply", status_code=status.HTTP_202_ACCEPTED)
async def reply(
    event_id: str, request: Request, relay: CurrentRelay, watch: CurrentWatch
) -> Response:
    """Keeps the reply and hands reply.execute to FCM for the paired Companion; 202 once FCM
    took it. The watch sends each reply once and shows nothing of the outcome (§8.4)."""
    body = await parse_body(request, relay.reply_parser)
    try:
        result = await relay.replies.send(body, event_id, watch.id)
    except UnknownEvent as error:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "not_found", "No such event", retryable=False
        ) from error
    except NoCompanion as error:
        raise invalid_token() from error
    if not result.ok:
        raise ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            f"FCM refused the message: {result.error or result.status}",
            retryable=False,
        )
    return Response(status_code=status.HTTP_202_ACCEPTED)
