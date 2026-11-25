import SwiftUI

@main
struct PersonalWatchApp: App {
    @WKApplicationDelegateAdaptor private var appDelegate: AppDelegate

    var body: some Scene {
        WindowGroup {
            RootScreen(pairing: appDelegate.pairing, registration: appDelegate.pushRegistration)
        }
    }
}
