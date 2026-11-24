"""Sends one alert push straight to APNs, to check delivery to the watch without the relay.

APNs credentials come from the APNS_* variables (see .env.example); arguments override
them. From the repo root:

    uv run --project relay --env-file .env send-test-push <device-token>
"""

import argparse
import asyncio
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from aioapns.exceptions import MaxAttemptsExceeded
from pydantic import ValidationError

from relay.apns import AlertPush, ApnsSender, ApnsSettings, PushResult

type Connect = Callable[[ApnsSettings], ApnsSender]


def build_parser() -> argparse.ArgumentParser:
    summary, _, details = __doc__.partition("\n\n")
    parser = argparse.ArgumentParser(
        prog="send-test-push",
        description=summary,
        epilog=details,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("device_token", help="hex APNs device token shown by the watch app")

    credentials = parser.add_argument_group("APNs credentials", "Override the APNS_* variables.")
    credentials.add_argument("--key-path", type=Path, help=".p8 auth key file")
    credentials.add_argument("--key-id")
    credentials.add_argument("--team-id")
    credentials.add_argument("--topic", help="bundle id of the watch app")
    credentials.add_argument(
        "--sandbox",
        dest="use_sandbox",
        action=argparse.BooleanOptionalAction,
        help="use the development APNs environment (default: production)",
    )

    push = parser.add_argument_group("push")
    push.add_argument("--title", default="Test push")
    push.add_argument("--body", help="default: the send time, to measure delivery delay")
    push.add_argument("--source-package", default="relay.test", help="also the thread id")
    push.add_argument("--replyable", action="store_true")
    push.add_argument(
        "--ttl",
        type=non_negative_int,
        default=3600,
        help="seconds APNs keeps the push while the watch is offline; 0 tries once",
    )
    return parser


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more, got {number}")
    return number


def main(argv: Sequence[str] | None = None, connect: Connect = ApnsSender.connect) -> int:
    """Console entry point; the exit code is 0 only when APNs accepted the push."""
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(parser, args)
    push = AlertPush(
        title=args.title,
        body=args.body or f"Sent at {datetime.now(UTC):%H:%M:%S} UTC",
        source_package=args.source_package,
        event_id=str(uuid.uuid4()),
        replyable=args.replyable,
    )

    try:
        result = asyncio.run(send(connect, settings, args.device_token, push, args.ttl))
    except MaxAttemptsExceeded:
        parser.exit(1, f"{parser.prog}: APNs unreachable, see the aioapns log above\n")

    print(f"apns-id: {result.apns_id}")
    print(f"status:  {result.status}")
    print(f"reason:  {result.reason or '-'}")
    return 0 if result.ok else 1


def load_settings(parser: argparse.ArgumentParser, args: argparse.Namespace) -> ApnsSettings:
    """Arguments win over APNS_* variables; a missing or invalid value exits with usage."""
    # Parser destinations are named after the ApnsSettings fields they override.
    overrides = {
        field: value
        for field in ApnsSettings.model_fields
        if (value := getattr(args, field)) is not None
    }
    try:
        return ApnsSettings(**overrides)
    except ValidationError as error:
        problems = "; ".join(
            f"APNS_{str(issue['loc'][0]).upper()}: {issue['msg']}" for issue in error.errors()
        )
        parser.error(problems)


async def send(
    connect: Connect, settings: ApnsSettings, device_token: str, push: AlertPush, ttl: int
) -> PushResult:
    # aioapns binds its connection pool to the running loop, so connect inside it.
    return await connect(settings).send(device_token, push, ttl)
