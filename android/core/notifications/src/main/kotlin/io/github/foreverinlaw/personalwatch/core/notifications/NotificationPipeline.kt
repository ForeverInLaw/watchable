package io.github.foreverinlaw.personalwatch.core.notifications

import io.github.foreverinlaw.personalwatch.core.protocol.EventAction
import io.github.foreverinlaw.personalwatch.core.protocol.EventActionType
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * Turns posted notifications into Notification events (TZ §4 F2, §7.3), or says why one is skipped.
 * Not thread-safe: the listener service calls it from its main thread.
 */
class NotificationPipeline(
    private val ownPackage: String,
    private val newEventId: () -> String = { UUID.randomUUID().toString() },
) {
    /**
     * What each active notification last showed, so a repost that brings nothing new is dropped:
     * apps re-post a notification on every update, and some re-post all of theirs at once.
     */
    private val shown = HashMap<String, ShownContent>()

    /** [activeNotifications] is read only when the group-summary rule needs it. */
    fun process(posted: PostedNotification, activeNotifications: () -> List<ActiveNotification>): PipelineResult {
        skipReason(posted, activeNotifications)?.let { return PipelineResult.Skip(it) }
        val content = posted.shownContent()
        val previous = shown.put(posted.key, content)
        return when {
            posted.lastMessage?.isFromUser == true -> PipelineResult.Skip(SkipReason.ECHO)
            previous == content -> PipelineResult.Skip(SkipReason.DUPLICATE)
            else -> PipelineResult.Forward(normalize(posted))
        }
    }

    /** The notification with [key] left the shade, so a later post with the same content is new. */
    fun forget(key: String) {
        shown.remove(key)
    }

    /**
     * The listener connected, at start or after an update or restart: what is in the shade now and
     * would be mirrored counts as already shown, so its reposts are not mirrored again, and
     * everything else is forgotten, as removals are not reported while the listener is unbound.
     */
    fun syncWithShade(active: List<PostedNotification>) {
        val shade = active.map { it.asActive() }
        shown.clear()
        active.filter { skipReason(it) { shade } == null }.associateTo(shown) { it.key to it.shownContent() }
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

/**
 * What a post shows, for dedup (TZ §4 F2). The chat's messages tell a new message apart from a
 * repost when both carry the same text.
 */
private data class ShownContent(val title: String?, val body: String?, val subtext: String?, val messages: List<Message>?)

private fun PostedNotification.shownContent() =
    ShownContent(displayTitle(), displayBody(), subText.cleaned(), conversation?.messages)

/** A chat is titled by its conversation, or by whoever wrote last in a direct chat. */
private fun PostedNotification.displayTitle(): String? {
    val conversation = conversation ?: return title.cleaned()
    return conversation.title.cleaned() ?: lastMessage?.sender.cleaned() ?: title.cleaned()
}

/** A chat shows its latest message; in a group chat the body names the sender. */
private fun PostedNotification.displayBody(): String? {
    val last = lastMessage ?: return bigText.cleaned() ?: text.cleaned()
    val sender = last.sender.cleaned()
    val text = last.text.cleaned()
    return if (conversation?.isGroup == true && sender != null) "$sender: ${text.orEmpty()}" else text
}

private val PostedNotification.lastMessage: Message?
    get() = conversation?.messages?.lastOrNull()

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

    /** Same key and content as the last post of a notification that is still active (TZ §4 F2). */
    DUPLICATE,

    /**
     * The chat was re-posted to show the user's own reply last (TZ §4 F2). It still counts as
     * shown, so the next incoming message is compared with it.
     */
    ECHO,
}
