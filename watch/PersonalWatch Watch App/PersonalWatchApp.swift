import SwiftUI

@main
struct PersonalWatchApp: App {
    @WKApplicationDelegateAdaptor private var appDelegate: AppDelegate

    var body: some Scene {
        WindowGroup {
            PushTokenScreen(registration: appDelegate.pushRegistration)
        }
    }
}
