package io.github.foreverinlaw.personalwatch.core.notifications

import io.github.foreverinlaw.personalwatch.core.protocol.EventAction
import io.github.foreverinlaw.personalwatch.core.protocol.EventActionType
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlin.time.Duration.Companion.seconds

/**
 * Turns posted notifications into Notification events (TZ §4 F2, §7.3), or says why one is skipped.
 * Not thread-safe: the listener service calls it from its main thread.
 */
class NotificationPipeline(
    private val ownPackage: String,
    private val newEventId: () -> String = { UUID.randomUUID().toString() },
) {
    private val recentPosts = RecentPosts<List<String?>>(DEDUP_WINDOW)

    /** [activeNotifications] is read only when the group-summary rule needs it. */
    fun process(posted: PostedNotification, activeNotifications: () -> List<ActiveNotification>): PipelineResult {
        skipReason(posted, activeNotifications)?.let { return PipelineResult.Skip(it) }
        val event = normalize(posted)
        val content = listOf(event.title, event.body, event.subtext)
        return if (recentPosts.recordAndCheckRepeat(posted.key, content, posted.postTime)) {
            PipelineResult.Skip(SkipReason.DUPLICATE)
        } else {
            PipelineResult.Forward(event)
        }
    }

    private fun skipReason(posted: PostedNotification, activeNotifications: () -> List<ActiveNotification>): SkipReason? =
        when {
            posted.packageName == ownPackage -> SkipReason.OWN
            posted.isOngoing -> SkipReason.ONGOING
            !posted.isClearable -> SkipReason.NOT_CLEARABLE
            posted.category == CATEGORY_CALL -> SkipReason.CALL
            posted.isGroupSummary && activeNotifications().any { it.isChildOf(posted) } -> SkipReason.SUMMARY_WITH_CHILDREN
            else -> null
        }

    private fun ActiveNotification.isChildOf(summary: PostedNotification) =
        !isGroupSummary && key != summary.key && groupKey == summary.groupKey

    private fun normalize(posted: PostedNotification): NotificationEvent {
        val replyAction = posted.actions.firstOrNull { it.acceptsFreeText }
        return NotificationEvent(
            eventId = newEventId(),
            sourcePackage = posted.packageName,
            sourceApp = posted.appLabel.cleaned(),
            notificationKey = posted.key,
            groupKey = posted.groupKey,
            // Whole seconds, like the relay's own timestamps and the protocol examples.
            postedAt = Instant.ofEpochMilli(posted.postTime).truncatedTo(ChronoUnit.SECONDS).toString(),
            title = posted.displayTitle(),
            body = posted.displayBody(),
            subtext = posted.subText.cleaned(),
            category = posted.category,
            isOngoing = posted.isOngoing,
            isClearable = posted.isClearable,
            isGroupSummary = posted.isGroupSummary,
            replyable = replyAction != null,
            actions = listOfNotNull(
                replyAction?.let { EventAction(REPLY_ACTION_ID, it.title.cleaned().orEmpty(), EventActionType.TEXT) },
            ),
        )
    }
}

/** A chat is titled by its conversation, or by whoever wrote last in a direct chat. */
private fun PostedNotification.displayTitle(): String? {
    val conversation = conversation ?: return title.cleaned()
    return conversation.title.cleaned() ?: conversation.messages.lastOrNull()?.sender.cleaned() ?: title.cleaned()
}

/** A chat shows its latest message; in a group chat the body names the sender. */
private fun PostedNotification.displayBody(): String? {
    val conversation = conversation
    val last = conversation?.messages?.lastOrNull() ?: return bigText.cleaned() ?: text.cleaned()
    val sender = last.sender.cleaned()
    val text = last.text.cleaned()
    return if (conversation.isGroup && sender != null) "$sender: ${text.orEmpty()}" else text
}

private const val REPLY_ACTION_ID = "reply"

/**
 * Null for blank text. Lone UTF-16 surrogates, which UTF-8 cannot encode and the relay refuses
 * (TZ §5.4), become U+FFFD.
 */
private fun String?.cleaned(): String? {
    if (isNullOrBlank()) return null
    val codePoints = codePoints().map { if (it in Char.MIN_SURROGATE.code..Char.MAX_SURROGATE.code) 0xFFFD else it }.toArray()
    return String(codePoints, 0, codePoints.size)
}

/** A repost of the same key and text within this window is a duplicate (TZ §4 F2). */
private val DEDUP_WINDOW = 5.seconds

/** Notification.CATEGORY_CALL: calls are out of scope (TZ §1.3). */
private const val CATEGORY_CALL = "call"

sealed interface PipelineResult {
    data class Forward(val event: NotificationEvent) : PipelineResult

    data class Skip(val reason: SkipReason) : PipelineResult
}

enum class SkipReason {
    /** Posted by the Companion itself. */
    OWN,
    ONGOING,

    /** Cannot be dismissed: an app's status while it works in the background, not a message. */
    NOT_CLEARABLE,
    CALL,

    /** The children of the group are shown instead (TZ §4 F2). */
    SUMMARY_WITH_CHILDREN,

    /** Same key and text as a post less than 5 seconds earlier. */
    DUPLICATE,
}
