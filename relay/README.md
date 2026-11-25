# Relay

Self-hosted relay between the Android companion and the watch app (`../docs/TZ.md` §9).
The watch and the Companion pair through it with a one-time code (TZ F1); each then
holds its own device token. The relay accepts Notification events from the paired
Companion at `POST /v1/events/notification`, keeps them in SQLite and pushes each one
to the paired watch through APNs. FCM, the outbox worker, retention and Docker Compose
follow §9.

## Running locally through a tunnel

The relay reads its settings from the repo-root `.env` (template: `.env.example`):
the `APNS_*` credentials, `PAIRING_SECRET` (at least 32 characters, the same value the
watch build carries; `openssl rand -base64 32` makes one), `DATABASE_URL` and
`PAIRING_TTL_SECONDS`. On startup it
creates the database and applies the migrations. From the repo root:

```bash
uv run --project relay --env-file .env uvicorn --factory relay.app:app_from_env --port 8000
```

`curl localhost:8000/healthz` answers `{"status":"ok"}` once the relay is up. To reach it
from the phone without a server, open a Cloudflare quick tunnel in a second terminal:

```bash
cloudflared tunnel --url http://localhost:8000
```

It prints a `https://<random>.trycloudflare.com` address that changes on every run; put
it in `android/local.properties` as `relay.url` and rebuild the Companion
(`../android/README.md`).

To pair by hand, start a session as the watch would, with the `PAIRING_SECRET` value
from `.env` and the protocol example in place of the watch's APNs token:

```bash
curl -s localhost:8000/v1/pair/start \
  -H "Authorization: Bearer <PAIRING_SECRET>" -H "Content-Type: application/json" \
  --data @protocol/examples/pair-start-request.json
```

The answer carries the 8-digit `pairing_code`. Complete the pairing as the Companion
would; the answer carries the `android_device_token`:

```bash
curl -s localhost:8000/v1/pair/complete -H "Content-Type: application/json" \
  --data '{"pairing_code": "<pairing_code>", "platform": "android"}'
```

Then post an event with that token:

```bash
curl -i localhost:8000/v1/events/notification \
  -H "Authorization: Bearer <android_device_token>" -H "Content-Type: application/json" \
  --data @protocol/examples/notification-event.json
```

The first post answers `202` and the paired watch gets the alert; the same `event_id`
again answers `409 duplicate` without a second push. The status codes are listed in
TZ §5.4. Pairing again revokes both earlier devices. Events stored before M2 carry
placeholder device ids and are not migrated; delete `data/relay.db` once to start clean.

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

The device token is the watch's APNs token, which the relay keeps after pairing: `push_token`
of the unrevoked `watchos` row in `devices` of `data/relay.db`. Groups separated by spaces
are accepted too. By default the body carries the
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
Autogenerate compares the tables in `tables.py` with a database at the latest revision,
such as the one the relay migrates on startup from the repo root:

```bash
DATABASE_URL=sqlite+aiosqlite:///../data/relay.db uv run alembic revision --autogenerate -m "..."
```
