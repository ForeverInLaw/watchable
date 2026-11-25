import Foundation

/// The relay URL and pairing secret CI builds into the app through Info.plist (TZ F1, §5.2).
struct RelayConfig: Sendable {
    let baseURL: URL
    let pairingSecret: String

    /// Nil when the build carries no usable URL or secret, so the app shows the relay as not configured.
    /// Only HTTPS: the requests carry the device token and reply text, and ATS does not guard IP hosts.
    /// The relay only accepts a secret of printable ASCII without spaces, which also fits in a header.
    init?(bundle: Bundle = .main) {
        guard
            let url = (bundle.object(forInfoDictionaryKey: "RelayURL") as? String).flatMap(URL.init(string:)),
            url.scheme == "https",
            url.host() != nil,
            let secret = bundle.object(forInfoDictionaryKey: "PairingSecret") as? String,
            !secret.isEmpty,
            secret.unicodeScalars.allSatisfy({ (0x21...0x7E).contains($0.value) })
        else { return nil }
        baseURL = url
        pairingSecret = secret
    }
}
