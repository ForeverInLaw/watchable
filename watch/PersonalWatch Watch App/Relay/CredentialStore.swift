import Foundation
import Security

/// What the watch keeps from a completed pairing (TZ F1).
struct Credentials: Codable, Equatable, Sendable {
    /// Path parameter of `POST /v1/devices/{id}/push-token`.
    let deviceId: String
    /// Bearer token of the watch.
    let token: String
    /// The APNs token the relay has, so a launch only sends a changed one.
    var apnsToken: String
}

/// Keeps the credentials in the Keychain, readable after the first unlock and never synced or migrated.
struct CredentialStore {
    /// Computed, since a dictionary of `Any` cannot be a shared constant under Swift 6 concurrency checks.
    private static var query: [CFString: Any] {
        [kSecClass: kSecClassGenericPassword, kSecAttrService: "relay", kSecAttrAccount: "watch"]
    }

    func load() -> Credentials? {
        var query = Self.query
        query[kSecReturnData] = true
        query[kSecMatchLimit] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else {
            return nil
        }
        return try? JSONDecoder().decode(Credentials.self, from: data)
    }

    /// Replaces the stored credentials; false if the Keychain refused them.
    func save(_ credentials: Credentials) -> Bool {
        guard let data = try? JSONEncoder().encode(credentials) else { return false }
        delete()
        var item = Self.query
        item[kSecValueData] = data
        item[kSecAttrAccessible] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(item as CFDictionary, nil) == errSecSuccess
    }

    func delete() {
        SecItemDelete(Self.query as CFDictionary)
    }
}
