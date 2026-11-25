package io.github.foreverinlaw.personalwatch.core.notifications

/**
 * A posted StatusBarNotification copied out of Android types, so filtering and normalization
 * run on the JVM. The listener service builds it; texts are already plain strings.
 */
data class PostedNotification(
    val key: String,
    val packageName: String,
    val appLabel: String?,
    /** The app's group, or null when the app did not group the notification. */
    val groupKey: String?,
    /** Epoch milliseconds. */
    val postTime: Long,
    val category: String?,
    val isOngoing: Boolean,
    val isClearable: Boolean,
    val isGroupSummary: Boolean,
    val title: String?,
    val text: String?,
    val bigText: String?,
    val subText: String?,
    /** Present when the notification uses MessagingStyle. */
    val conversation: Conversation?,
    val actions: List<PostedAction>,
)

/** MessagingStyle content: messages are oldest first. */
data class Conversation(
    val title: String?,
    val isGroup: Boolean,
    val messages: List<Message>,
)

data class Message(
    val sender: String?,
    val text: String?,
    /** Sent by the user of the phone (MessagingStyle.user), not by the other side of the chat. */
    val isFromUser: Boolean = false,
)

data class PostedAction(
    val title: String?,
    /** The action has a RemoteInput that accepts free-form text. */
    val acceptsFreeText: Boolean,
)

/** The fields of another active notification that the group-summary rule looks at. */
data class ActiveNotification(
    val key: String,
    val groupKey: String?,
    val isGroupSummary: Boolean,
)

/** How this notification looks to the group-summary rule while it is in the shade. */
fun PostedNotification.asActive() = ActiveNotification(key, groupKey, isGroupSummary)
