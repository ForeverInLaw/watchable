package io.github.foreverinlaw.personalwatch.companion

import android.app.Notification
import android.service.notification.StatusBarNotification
import androidx.core.app.NotificationCompat
import io.github.foreverinlaw.personalwatch.core.notifications.ActiveNotification
import io.github.foreverinlaw.personalwatch.core.notifications.Conversation
import io.github.foreverinlaw.personalwatch.core.notifications.Message
import io.github.foreverinlaw.personalwatch.core.notifications.PostedAction
import io.github.foreverinlaw.personalwatch.core.notifications.PostedNotification

/** Copies what the pipeline reads out of the Android types (TZ §7.3). */
fun StatusBarNotification.toPostedNotification(appLabel: String?): PostedNotification {
    val extras = notification.extras
    return PostedNotification(
        key = key,
        packageName = packageName,
        appLabel = appLabel,
        groupKey = groupKeyOrNull(),
        postTime = postTime,
        category = notification.category,
        isOngoing = isOngoing,
        isClearable = isClearable,
        isGroupSummary = NotificationCompat.isGroupSummary(notification),
        title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString(),
        text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString(),
        bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString(),
        subText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString(),
        conversation = NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(notification)?.let { style ->
            Conversation(
                title = style.conversationTitle?.toString(),
                isGroup = style.isGroupConversation,
                messages = style.messages.map {
                    Message(
                        sender = it.person?.name?.toString(),
                        text = it.text?.toString(),
                        // MessagingStyle leaves the sender null for the user's messages; some apps pass the user instead.
                        isFromUser = it.person == null || it.person == style.user,
                    )
                },
            )
        },
        actions = notification.actions.orEmpty().map { action ->
            PostedAction(
                title = action.title?.toString(),
                acceptsFreeText = action.remoteInputs.orEmpty().any { it.allowFreeFormInput },
            )
        },
    )
}

fun StatusBarNotification.toActiveNotification() = ActiveNotification(
    key = key,
    groupKey = groupKeyOrNull(),
    isGroupSummary = NotificationCompat.isGroupSummary(notification),
)

/** The group the app or the system's auto-grouping put the notification in, if any. */
private fun StatusBarNotification.groupKeyOrNull(): String? = if (isGroup) groupKey else null
