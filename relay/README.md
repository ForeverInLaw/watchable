# Relay

Self-hosted relay between the Android companion and the watch app (`../docs/TZ.md` §9).
It accepts Notification events from the Companion at `POST /v1/events/notification`,
keeps them in SQLite and pushes each one to the watch through APNs. Until pairing (M2)
the Companion authenticates with one static bearer token and the watch push token is
set by hand; FCM, the outbox worker, retention and Docker Compose follow §9.

## Running locally through a tunnel

The relay reads its settings from the repo-root `.env` (template: `.env.example`):
the `APNS_*` credentials, `RELAY_TOKEN` (the bearer token the Companion sends),
`WATCH_PUSH_TOKEN` (the device token the watch app shows, with or without the spaces
between groups) and `DATABASE_URL`. On startup it creates the database and applies the
migrations. From the repo root:

```bash
uv run --project relay --env-file .env uvicorn --factory relay.app:app_from_env --port 8000
```

`curl localhost:8000/healthz` answers `{"status":"ok"}` once the relay is up. To reach it
from the phone without a server, open a Cloudflare quick tunnel in a second terminal:

```bash
cloudflared tunnel --url http://localhost:8000
```

It prints a `https://<random>.trycloudflare.com` address that changes on every run; enter
it in the Companion as the relay URL, together with `RELAY_TOKEN`. To send an event by
hand, post the protocol example with the `RELAY_TOKEN` value from `.env`:

```bash
curl -i https://<random>.trycloudflare.com/v1/events/notification \
  -H "Authorization: Bearer <RELAY_TOKEN>" -H "Content-Type: application/json" \
  --data @protocol/examples/notification-event.json
```

The first post answers `202` and the watch shows the alert; the same `event_id` again
answers `409 duplicate` without a second push. The status codes are listed in TZ §5.4.

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

Schema changes go into a new Alembic revision in `src/relay/migrations/versions`.
Autogenerate compares the tables in `store.py` with a database at the latest revision,
such as the one the relay migrates on startup from the repo root:

```bash
DATABASE_URL=sqlite+aiosqlite:///../data/relay.db uv run alembic revision --autogenerate -m "..."
```
