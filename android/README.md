# Android

The Companion: Kotlin + Jetpack Compose (`../docs/TZ.md` §7). It listens for notifications,
filters and normalizes them into Notification events (§4 F2) and posts them to the relay once
paired with the watch (§4 F1). Foreground service, FCM and Room come in later stages.

## Modules

- `app` — notification listener service, status screen, wiring.
- `core/protocol` — protocol bodies; tests check them against `../protocol/schema`.
- `core/notifications` — filters, dedup and normalization, free of Android types.
- `core/network` — relay HTTP client, the pairing credentials in DataStore and the retrying uploader.

## Build

Needs JDK 21 and an Android SDK with platform 37.1 (`sdk.dir` in `local.properties`).

```bash
./gradlew :app:assembleDebug
./gradlew test
```

## Relay URL and pairing

The relay URL is baked into the build from the gitignored `local.properties`:

```properties
relay.url=https://watch.but.red
```

Without it the app builds and the status screen shows the relay as not configured. A new
URL means a rebuild. After installing, grant notification access from the status screen, then
tap "Ввести код с часов" and enter the 8-digit code the watch shows. The device token from
pairing lives in DataStore under `files/`, which backup and device transfer skip. Until paired,
notifications are not sent; a token the relay revokes (another phone paired) drops the
Companion back to unpaired.
