# Relay

Self-hosted relay between the Android companion and the watch app (`../docs/TZ.md` §9).
So far it holds only the APNs client and a script that sends a test push with it; the
FastAPI app, SQLite storage, pairing, FCM, the outbox worker and Docker Compose follow §9.

## Test push

`send-test-push` sends one alert push (payload and headers per TZ §5.5) straight to APNs
and prints the `apns-id`, HTTP status and rejection reason. The exit code is 0 only when
APNs accepted the push.

The APNs credentials come from the `APNS_*` variables in the repo-root `.env`
(template: `.env.example`); `--key-path`, `--key-id`, `--team-id`, `--topic` and
`--sandbox` override them. Production APNs is the default. From the repo root:

```bash
uv run --project relay --env-file .env send-test-push <device-token>
```

The device token is the hex string the watch app shows in groups of 8; pass it whole or
as the groups. By default the body carries the
send time, so the delay is visible on the watch, and APNs keeps the push for an hour
while the watch is offline (`--ttl 0` tries once). See `--help` for the payload options.

## Development

```bash
cd relay
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
uv run pytest
```
