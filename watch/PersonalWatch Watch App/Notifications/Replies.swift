import Foundation
import os
import UserNotifications

/// The reply action of replyable alerts; the relay puts this category on them (TZ F3, §8.3).
enum ReplyCategory {
    static let identifier = "MESSAGE_REPLY"
    static let actionIdentifier = "REPLY"

    /// Dictation or Scribble; the text goes to the relay without opening the app.
    static var category: UNNotificationCategory {
        let reply = UNTextInputNotificationAction(
            identifier: actionIdentifier,
            title: "Ответить",
            options: [],
            textInputButtonTitle: "Отправить",
            textInputPlaceholder: "Ответ"
        )
        return UNNotificationCategory(identifier: identifier, actions: [reply], intentIdentifiers: [], options: [])
    }
}

/// Sends a reply the user entered on an alert to the relay: one request, no retry,
/// and nothing shown of the outcome (TZ §8.4). The relay keeps what became of it;
/// the log says why a reply never left the watch, and never holds the reply text.
struct ReplySender {
    private static let log = Logger(subsystem: "io.github.foreverinlaw.personalwatch", category: "Reply")

    func send(text: String, toEvent eventId: String) async {
        guard !text.isEmpty else {
            Self.log.notice("reply to event \(eventId, privacy: .public) dropped: no text")
            return
        }
        guard let config = RelayConfig() else {
            Self.log.error("reply to event \(eventId, privacy: .public) dropped: the build has no relay")
            return
        }
        guard let credentials = CredentialStore().load() else {
            Self.log.notice("reply to event \(eventId, privacy: .public) dropped: not paired")
            return
        }
        let reply = Reply(replyId: UUID().uuidString.lowercased(), text: text, sentAt: Date.now.formatted(.iso8601))
        do {
            try await RelayClient(config: config).sendReply(reply, toEvent: eventId, as: credentials)
            Self.log.info("reply \(reply.replyId, privacy: .public) to event \(eventId, privacy: .public): taken")
        } catch {
            // Fire and forget: the watch neither retries nor reports a failed reply.
            Self.log.error("reply \(reply.replyId, privacy: .public) to event \(eventId, privacy: .public): \(String(describing: error), privacy: .public)")
        }
    }
}
