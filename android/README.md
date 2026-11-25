# Android

The Companion: Kotlin + Jetpack Compose (`../docs/TZ.md` §7). It listens for notifications,
filters and normalizes them into Notification events (§4 F2) and posts them to the relay.
Foreground service, FCM, Room and pairing come in later stages.

## Modules

- `app` — notification listener service, status screen, wiring.
- `core/protocol` — protocol bodies; tests check them against `../protocol/schema`.
- `core/notifications` — filters, dedup and normalization, free of Android types.
- `core/network` — relay HTTP client and the retrying uploader.

## Build

Needs JDK 21 and an Android SDK with platform 37.1 (`sdk.dir` in `local.properties`).

```bash
./gradlew :app:assembleDebug
./gradlew test
```

## Relay URL and token

Until pairing (M2) the relay URL and its static bearer token are baked into the build from
the gitignored `local.properties`:

```properties
relay.url=https://<random>.trycloudflare.com
relay.token=<RELAY_TOKEN from the repo-root .env>
```

Without them the app builds and the status screen shows the relay as not configured. A new
tunnel URL means a rebuild. After installing, grant notification access from the status screen.
