# watchOS

Independent (watch-only) SwiftUI app for watchOS 10. The Xcode project is generated
from `project.yml` with [XcodeGen](https://github.com/yonaskolb/XcodeGen) and is not committed.

```bash
cd watch
xcodegen generate
xcodebuild -project PersonalWatch.xcodeproj -scheme PersonalWatch \
  -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```

There is no local Mac: CI builds every PR that touches `watch/` unsigned, and a push to `main`, a `v1.2.3` tag or a
manual run of the `watch` workflow signs the app and uploads it to TestFlight
(`.github/workflows/watch.yml`, `../docs/TZ.md` §12.3). To try a branch on the watch before
merging:

```bash
gh workflow run watch.yml --ref <branch>
```

The icon in `Assets.xcassets` is a placeholder.

- `PersonalWatch` — empty iOS wrapper Xcode needs to package a watch-only app.
- `PersonalWatch Watch App` — the app. The bundle id is set once, in `APP_BUNDLE_ID`
  in `project.yml`; the watch app id (the APNs topic) is that plus `.watchkitapp`.

The app asks for notification permission and registers with APNs. Unpaired, it calls the
relay's `pair/start` with the pairing secret, shows the 8-digit code for the Companion and
polls `pair/status` until the code is entered; the device token then lives in the Keychain and
the screen shows «Подключено» with a re-pair button. A paired watch sends its APNs token to the
relay on launch when it changed. Incoming pushes are shown as regular notifications, including
while the app is open. An alert the relay marks replyable (category `MESSAGE_REPLY`) has an
«Ответить» action: the text from dictation or Scribble goes to the relay in one
`POST /v1/events/{event_id}/reply` with a new `reply_id` and a 10-second timeout. The watch does
not retry it and shows no status; the relay keeps what became of the reply.

## Relay URL and pairing secret

Both come from CI: the `RELAY_URL` repository variable and the `PAIRING_SECRET` secret (the same
value as in the relay's `.env`) are passed to the TestFlight archive as build settings, which
`PersonalWatch Watch App/Info.plist` puts into the bundle. PR builds and
`gh workflow run watch.yml --ref <branch> -f testflight=false` (an unsigned build of a branch)
carry neither, so that app shows «Relay не настроен».

See `../docs/TZ.md` §8.
