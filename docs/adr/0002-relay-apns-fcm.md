# APNs for watch delivery, FCM for phone commands

Watch notifications are delivered by APNs directly to the watch app, with the self-hosted relay storing and retrying events. Phone-bound commands (replies, music, find) go through FCM HTTP v1 only: a WebSocket fallback would need a foreground service, a battery optimization exemption and a heartbeat to survive Doze, while FCM rides the shared Play Services connection (decided in M3). APNs is the only reliable way to wake the watch app in the background; background BLE is limited to five timely alerts per day.

## Consequences

- The relay depends on Apple APNs and Google FCM credentials.
- A2093 without LTE needs Wi-Fi or a nearby iPhone to receive pushes.
- FCM adds a Google dependency to an otherwise self-hosted relay.
