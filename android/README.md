# Android

The Companion: Kotlin + Jetpack Compose (`../docs/TZ.md` §7). It listens for notifications,
filters and normalizes them into Notification events (§4 F2) and posts them to the relay once
paired with the watch (§4 F1). Replies from the watch arrive over FCM as `reply.execute`, and
the Companion sends each one through the reply action of the notification it answers and reports
the result to the relay; a message FCM delivers again is dropped by its envelope id (§4 F3,
§7.4). The foreground service comes in a later stage.

## Modules

- `app` — notification listener and FCM services, reply execution, status screen, wiring.
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

## Firebase

FCM needs a Firebase project with an Android app registered for
`io.github.foreverinlaw.personalwatch.companion`. The app does not use the google-services plugin,
and no `google-services.json` is committed: Firebase starts in `CompanionApp` from four values in
`local.properties`, which the `google-services.json` the Firebase console offers for that app
carries:

```properties
firebase.project_id=<project_info.project_id>
firebase.app_id=<client[].client_info.mobilesdk_app_id>
firebase.api_key=<client[].api_key[].current_key>
firebase.sender_id=<project_info.project_number>
```

The same values are in the Firebase console under Project settings → General → Your apps
(App ID, Project ID, Web API key) and Cloud Messaging (Sender ID). Without all four the app builds,
CI included, and the status screen shows FCM as not configured. Configured, the Companion sends
its FCM token in pairing and again whenever Firebase hands out a new one. The relay sends FCM
with a service account of the same project (`../relay/README.md`).

Replies need notification access: the Companion finds the notification in the shade of the
connected listener by its key.
