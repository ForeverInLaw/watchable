import Foundation
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
/// and nothing shown of the outcome (TZ §8.4). The relay keeps what became of it.
struct ReplySender {
    func send(text: String, toEvent eventId: String) async {
        guard !text.isEmpty, let config = RelayConfig(), let credentials = CredentialStore().load() else { return }
        let reply = Reply(replyId: UUID().uuidString.lowercased(), text: text, sentAt: Date.now.formatted(.iso8601))
        do {
            try await RelayClient(config: config).sendReply(reply, toEvent: eventId, as: credentials)
        } catch {
            // Fire and forget: the watch neither retries nor reports a failed reply.
        }
    }
}
