import UserNotifications
import WatchKit

/// Receives the app lifecycle and APNs callbacks that SwiftUI has no API for
/// and forwards them to `PushRegistration`, `Pairing` and `ReplySender`.
@MainActor
final class AppDelegate: NSObject, WKApplicationDelegate, UNUserNotificationCenterDelegate {
    let pushRegistration = PushRegistration()
    let pairing = Pairing()

    func applicationDidFinishLaunching() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.setNotificationCategories([ReplyCategory.category])
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

    /// Sends the text of a reply action to the relay (TZ §8.4); the system waits for the request,
    /// which gives up after 10 seconds. Other responses only open the app.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        guard
            let reply = response as? UNTextInputNotificationResponse,
            reply.actionIdentifier == ReplyCategory.actionIdentifier,
            let eventId = reply.notification.request.content.userInfo["event_id"] as? String
        else { return }
        let text = reply.userText
        await ReplySender().send(text: text, toEvent: eventId)
    }
}
