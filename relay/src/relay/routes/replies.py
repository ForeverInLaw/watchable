"""Replies from the watch and what the Companion made of them (docs/TZ.md F3, §5.6)."""

from fastapi import APIRouter, Request, Response, status

from relay.api import (
    ApiError,
    CurrentAndroid,
    CurrentRelay,
    CurrentWatch,
    invalid_token,
    parse_body,
)
from relay.replies import (
    DuplicateReply,
    InvalidReply,
    NoCompanion,
    Undelivered,
    UnknownEvent,
    UnknownReply,
)

router = APIRouter()


@router.post("/v1/events/{event_id}/reply", status_code=status.HTTP_202_ACCEPTED)
async def reply(
    event_id: str, request: Request, relay: CurrentRelay, watch: CurrentWatch
) -> Response:
    """Keeps the reply and hands reply.execute to FCM for the paired Companion; 202 once FCM
    took it. The watch sends each reply once and shows nothing of the outcome (§8.4)."""
    retry_after = relay.reply_limit.admit()
    if retry_after is not None:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many replies",
            retryable=True,
            retry_after=retry_after,
        )
    body = await parse_body(request, relay.reply_parser)
    try:
        await relay.replies.send(body, event_id, watch.id)
    except UnknownEvent as error:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "not_found", "No such event", retryable=False
        ) from error
    except InvalidReply as error:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "invalid_request", str(error), retryable=False
        ) from error
    except DuplicateReply as error:
        raise ApiError(
            status.HTTP_409_CONFLICT, "duplicate", "Reply already sent", retryable=False
        ) from error
    except NoCompanion as error:
        raise invalid_token() from error
    except Undelivered as error:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            error.reason,
            str(error),
            retryable=error.retryable,
        ) from error
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/v1/replies/{reply_id}/result", status_code=status.HTTP_204_NO_CONTENT)
async def reply_result(
    reply_id: str, request: Request, relay: CurrentRelay, android: CurrentAndroid
) -> Response:
    """The Companion reports whether it sent the reply; nothing of it reaches the watch."""
    body = await parse_body(request, relay.result_parser)
    try:
        await relay.replies.complete(reply_id, android.id, body)
    except UnknownReply as error:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "not_found", "No such reply", retryable=False
        ) from error
    except DuplicateReply as error:
        raise ApiError(
            status.HTTP_409_CONFLICT, "duplicate", "Reply already has a result", retryable=False
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
