import Foundation
import Observation
import WatchKit

/// Pairs the watch with the Companion through the relay and keeps the pairing (TZ F1).
/// `AppDelegate` drives it from launch and the APNs callbacks; `RootScreen` shows `state`.
@MainActor
@Observable
final class Pairing {
    enum State: Equatable {
        /// The build carries no usable relay URL or pairing secret.
        case notConfigured
        /// Unpaired; pair/start needs the APNs token, which is still on its way.
        case waitingForPushToken
        case starting
        /// The code the user enters in the Companion.
        case showingCode(String)
        /// pair/start found no network.
        case offline
        /// The relay refused the pairing secret built into the app; retrying will not help.
        case secretMismatch
        /// The Keychain refused the credentials of a completed pairing.
        case storageFailed
        case failed(RelayError)
        case connected
    }

    private(set) var state = State.waitingForPushToken
    /// The credentials of the current pairing stay until a new pairing completes,
    /// so a re-pair can be abandoned.
    private var credentials: Credentials?
    private var pushToken: DeviceToken?

    private let relay = RelayConfig().map { RelayClient(config: $0) }
    private let store = CredentialStore()
    @ObservationIgnored private var pairingTask: Task<Void, Never>?

    nonisolated init() {}

    /// A re-pair is under way and can be abandoned for the current pairing.
    var canCancel: Bool { credentials != nil && state != .connected }
    var canStartPairing: Bool { relay != nil && pushToken != nil }

    /// Shows the stored pairing, if any; called once at launch.
    func start() {
        guard relay != nil else {
            state = .notConfigured
            return
        }
        credentials = store.load()
        state = credentials == nil ? .waitingForPushToken : .connected
    }

    /// An unpaired watch starts pairing; a paired one sends the relay a changed token (TZ F1).
    func didReceive(pushToken token: DeviceToken) {
        pushToken = token
        guard let relay else { return }
        if let credentials {
            if credentials.apnsToken != token.hex {
                Task { await updatePushToken(token, of: credentials, relay: relay) }
            }
        } else if state == .waitingForPushToken {
            startPairing()
        }
    }

    /// Asks the relay for a new code: on the first launch, on retry and on re-pair.
    func startPairing() {
        guard let relay, let pushToken else { return }
        pairingTask?.cancel()
        state = .starting
        pairingTask = Task { await pair(relay: relay, pushToken: pushToken) }
    }

    /// Abandons a re-pair; the current pairing stays.
    func cancelPairing() {
        guard credentials != nil else { return }
        pairingTask?.cancel()
        pairingTask = nil
        state = .connected
    }

    /// Starts sessions until the Companion enters a code: an expired session is replaced by a new one.
    private func pair(relay: RelayClient, pushToken: DeviceToken) async {
        while !Task.isCancelled {
            let session: PairingSession
            do throws(RelayError) {
                session = try await relay.startPairing(apnsToken: pushToken.hex, name: deviceName)
            } catch {
                if !Task.isCancelled { show(error) }
                return
            }
            guard !Task.isCancelled else { return }
            state = .showingCode(session.pairingCode)
            switch await waitForCompanion(session, relay: relay) {
            case .paired:
                finish(session, pushToken: pushToken)
                return
            case .expired:
                continue
            case .cancelled:
                return
            }
        }
    }

    private enum Wait { case paired, expired, cancelled }

    /// Polls pair/status every 2 seconds while the code is on screen (TZ F1).
    private func waitForCompanion(_ session: PairingSession, relay: RelayClient) async -> Wait {
        while true {
            do {
                try await Task.sleep(for: .seconds(2))
            } catch {
                return .cancelled
            }
            do throws(RelayError) {
                if try await relay.isPaired(session) { return .paired }
            } catch {
                switch error {
                // The network or the relay may come back before the code expires.
                case .unreachable: continue
                case .refused(let status, _) where status >= 500: continue
                // pairing_expired, or anything else that ends this session.
                default: return .expired
                }
            }
        }
    }

    private func finish(_ session: PairingSession, pushToken: DeviceToken) {
        pairingTask = nil
        let paired = Credentials(deviceId: session.watchDeviceId, token: session.watchDeviceToken, apnsToken: pushToken.hex)
        guard store.save(paired) else {
            state = .storageFailed
            return
        }
        credentials = paired
        state = .connected
    }

    private func show(_ error: RelayError) {
        switch error {
        case .unreachable: state = .offline
        case .refused(401, "invalid_pairing_secret"?): state = .secretMismatch
        default: state = .failed(error)
        }
    }

    private func updatePushToken(_ token: DeviceToken, of current: Credentials, relay: RelayClient) async {
        do throws(RelayError) {
            try await relay.updatePushToken(token.hex, of: current)
        } catch .refused(401, "invalid_token"?) {
            // A later pairing revoked this watch (TZ §5.10): forget it and pair again.
            guard credentials == current else { return }
            store.delete()
            credentials = nil
            if state == .connected { startPairing() }
            return
        } catch {
            return // The next launch sends it again.
        }
        // A pairing that completed meanwhile already gave the relay its own token.
        guard credentials == current else { return }
        var updated = current
        updated.apnsToken = token.hex
        if store.save(updated) { credentials = updated }
    }

    /// Tells devices apart on the relay; the schema takes 1 to 100 characters.
    private var deviceName: String {
        let name = String(WKInterfaceDevice.current().name.prefix(100))
        return name.isEmpty ? "Apple Watch" : name
    }
}
