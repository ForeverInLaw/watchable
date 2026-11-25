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

The app asks for notification permission, registers with APNs, and shows the device
token as a QR code and as hex text. Incoming pushes are shown as regular notifications,
including while the app is open. Relay client, pairing and reply actions come later.

See `../docs/TZ.md` §8.
