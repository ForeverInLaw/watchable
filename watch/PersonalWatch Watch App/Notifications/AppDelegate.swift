import UserNotifications
import WatchKit

/// Receives the app lifecycle and APNs callbacks that SwiftUI has no API for
/// and forwards them to `PushRegistration` and `Pairing`.
@MainActor
final class AppDelegate: NSObject, WKApplicationDelegate, UNUserNotificationCenterDelegate {
    let pushRegistration = PushRegistration()
    let pairing = Pairing()

    func applicationDidFinishLaunching() {
        UNUserNotificationCenter.current().delegate = self
        pairing.start()
        Task { await pushRegistration.start() }
    }

    func didRegisterForRemoteNotifications(withDeviceToken deviceToken: Data) {
        pushRegistration.didRegister(deviceToken: deviceToken)
        pairing.didReceive(pushToken: DeviceToken(deviceToken))
    }

    func didFailToRegisterForRemoteNotificationsWithError(_ error: any Error) {
        pushRegistration.didFailToRegister(error)
    }

    /// Shows a push as a regular notification even while the app is open;
    /// without this watchOS delivers it silently to the foreground app.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }
}
