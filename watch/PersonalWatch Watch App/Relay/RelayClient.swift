import Foundation

/// Why a relay request did not succeed (TZ §5.10).
enum RelayError: Error, Equatable {
    /// No answer: the watch is offline or the relay cannot be reached.
    case unreachable
    /// The relay answered with `status` and, if it sent the protocol error body, its `code`.
    case refused(status: Int, code: String?)
    /// A 2xx answer whose body does not match the protocol; retrying will not fix it.
    case malformedAnswer
}

/// Answer to `POST /v1/pair/start` (protocol/schema/pair-start-response.schema.json).
struct PairingSession: Decodable, Sendable {
    let pairingId: String
    let pairingCode: String
    let watchDeviceId: String
    let watchDeviceToken: String
}

/// The relay endpoints the watch calls (TZ F1, §5.2). Bodies use snake_case keys.
struct RelayClient: Sendable {
    let config: RelayConfig

    /// Asks for a pairing code with the pairing secret; the open session on the relay closes.
    func startPairing(apnsToken: String, name: String) async throws(RelayError) -> PairingSession {
        struct Body: Encodable {
            let platform = "watchos"
            let apnsToken: String
            let name: String
        }
        let request = post("v1/pair/start", bearer: config.pairingSecret, body: Body(apnsToken: apnsToken, name: name))
        return try decode(PairingSession.self, from: await exchange(request))
    }

    /// Whether the Companion has entered the code; `404 pairing_expired` once the session is over.
    func isPaired(_ session: PairingSession) async throws(RelayError) -> Bool {
        struct Status: Decodable { let paired: Bool }
        let url = config.baseURL.appending(path: "v1/pair/status")
            .appending(queryItems: [URLQueryItem(name: "pairing_id", value: session.pairingId)])
        let request = authorized(URLRequest(url: url), bearer: session.watchDeviceToken)
        return try decode(Status.self, from: await exchange(request)).paired
    }

    /// Replaces the watch's APNs token on the relay.
    func updatePushToken(_ apnsToken: String, of credentials: Credentials) async throws(RelayError) {
        struct Body: Encodable { let pushToken: String }
        let path = "v1/devices/\(credentials.deviceId)/push-token"
        _ = try await exchange(post(path, bearer: credentials.token, body: Body(pushToken: apnsToken)))
    }

    private func post(_ path: String, bearer: String, body: some Encodable) -> URLRequest {
        var request = authorized(URLRequest(url: config.baseURL.appending(path: path)), bearer: bearer)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        request.httpBody = try? encoder.encode(body)
        return request
    }

    private func authorized(_ request: URLRequest, bearer: String) -> URLRequest {
        var request = request
        request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        return request
    }

    /// Sends `request` and returns the body of a 2xx answer.
    private func exchange(_ request: URLRequest) async throws(RelayError) -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw .unreachable
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            struct ErrorBody: Decodable {
                struct Detail: Decodable { let code: String }
                let error: Detail
            }
            throw .refused(status: status, code: try? JSONDecoder().decode(ErrorBody.self, from: data).error.code)
        }
        return data
    }

    private func decode<Answer: Decodable>(_ type: Answer.Type, from data: Data) throws(RelayError) -> Answer {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let answer = try? decoder.decode(type, from: data) else {
            throw .malformedAnswer
        }
        return answer
    }
}
