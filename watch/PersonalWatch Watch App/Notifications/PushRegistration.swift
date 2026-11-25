import Foundation
import Observation
import UserNotifications
import WatchKit

/// APNs device token in the lowercase hex form the APNs HTTP/2 API takes in its request path.
struct DeviceToken: Equatable {
    let hex: String

    init(_ data: Data) {
        hex = data.map { String(format: "%02x", $0) }.joined()
    }
}

/// Notification permission and APNs registration state, shown while the watch waits to pair.
/// `AppDelegate` drives it from the system callbacks.
@MainActor
@Observable
final class PushRegistration {
    enum Status: Equatable {
        case requestingPermission
        case permissionDenied
        case registering
        case registered(DeviceToken)
        case failed(String)
    }

    private(set) var status = Status.requestingPermission

    nonisolated init() {}

    /// Asks for alert permission, then registers with APNs. Apple recommends registering on every launch.
    func start() async {
        status = .requestingPermission
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound, .badge])
            guard granted else {
                status = .permissionDenied
                return
            }
        } catch {
            status = .failed(error.localizedDescription)
            return
        }
        status = .registering
        WKApplication.shared().registerForRemoteNotifications()
    }

    func didRegister(deviceToken: Data) {
        status = .registered(DeviceToken(deviceToken))
    }

    func didFailToRegister(_ error: any Error) {
        status = .failed(error.localizedDescription)
    }
}
