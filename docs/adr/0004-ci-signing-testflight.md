# Watch app is built, signed and shipped from GitHub Actions

There is no local Mac, so the watch app is built on a GitHub Actions macOS runner, signed there with a distribution certificate and provisioning profile stored in GitHub Actions secrets, and uploaded to TestFlight with an App Store Connect API key. The paired iPhone installs it from TestFlight. The repository is public, so the signing job runs only on pushes to `main`, on tags and on a manual dispatch, which needs write access; never on pull requests, including those from forks.

## Consequences

- No Xcode debugger or live device console; the watch app reports its diagnostics to the relay.
- Each iteration on the watch side waits for a CI build and TestFlight processing.
- TestFlight builds receive production APNs tokens, so the relay uses production APNs.
- TestFlight builds expire after 90 days and must be refreshed by a new upload.
