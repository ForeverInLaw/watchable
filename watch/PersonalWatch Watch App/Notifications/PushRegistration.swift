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

    /// `hex` in space-separated groups of 8 for reading off the screen: lines wrap at
    /// the spaces, so SwiftUI never hyphenates the token. `send-test-push` accepts this form.
    var groupedHex: String {
        let digits = Array(hex)
        return stride(from: 0, to: digits.count, by: 8)
            .map { String(digits[$0..<min($0 + 8, digits.count)]) }
            .joined(separator: " ")
    }
}

/// Notification permission and APNs registration state, shown on the main screen.
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
