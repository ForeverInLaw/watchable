package io.github.foreverinlaw.personalwatch.core.notifications

import io.github.foreverinlaw.personalwatch.core.protocol.EventAction
import io.github.foreverinlaw.personalwatch.core.protocol.EventActionType
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import org.junit.Assert.assertEquals
import org.junit.Test

class NotificationPipelineTest {
    private val pipeline = NotificationPipeline(ownPackage = "io.example.companion", newEventId = { "event-1" })

    private val mail = PostedNotification(
        key = "0|org.example.mail|7|null|10001",
        packageName = "org.example.mail",
        appLabel = "Mail",
        groupKey = null,
        postTime = 1_795_595_400_250, // 2026-11-25T08:30:00.250Z
        category = "email",
        isOngoing = false,
        isClearable = true,
        isGroupSummary = false,
        title = "Invoice",
        text = "Your invoice is ready",
        bigText = null,
        subText = "work@example.org",
        conversation = null,
        actions = emptyList(),
    )

    private fun process(posted: PostedNotification, active: List<ActiveNotification> = emptyList()) =
        pipeline.process(posted) { active }

    @Test
    fun `a plain notification becomes a Notification event`() {
        assertEquals(
            PipelineResult.Forward(
                NotificationEvent(
                    eventId = "event-1",
                    sourcePackage = "org.example.mail",
                    sourceApp = "Mail",
                    notificationKey = "0|org.example.mail|7|null|10001",
                    groupKey = null,
                    postedAt = "2026-11-25T08:30:00.250Z",
                    title = "Invoice",
                    body = "Your invoice is ready",
                    subtext = "work@example.org",
                    category = "email",
                    isOngoing = false,
                    isClearable = true,
                    isGroupSummary = false,
                    replyable = false,
                    actions = emptyList(),
                ),
            ),
            process(mail),
        )
    }

    @Test
    fun `the Companion's own notifications are skipped`() {
        assertEquals(
            PipelineResult.Skip(SkipReason.OWN),
            process(mail.copy(packageName = "io.example.companion")),
        )
    }

    @Test
    fun `ongoing notifications are skipped`() {
        assertEquals(PipelineResult.Skip(SkipReason.ONGOING), process(mail.copy(isOngoing = true)))
    }

    @Test
    fun `calls are skipped even when the app does not mark them ongoing`() {
        assertEquals(PipelineResult.Skip(SkipReason.CALL), process(mail.copy(category = "call")))
    }

    private val chatSummary = mail.copy(key = "0|org.example.chat|0|g:chats|10001", groupKey = "0|org.example.chat|g:chats", isGroupSummary = true)

    @Test
    fun `a group summary is skipped while a child of its group is active`() {
        val child = ActiveNotification(key = "0|org.example.chat|5|g:chats|10001", groupKey = chatSummary.groupKey, isGroupSummary = false)

        assertEquals(
            PipelineResult.Skip(SkipReason.SUMMARY_WITH_CHILDREN),
            process(chatSummary, active = listOf(chatSummary.asActive(), child)),
        )
    }

    @Test
    fun `a group summary without active children is forwarded`() {
        val otherGroup = ActiveNotification(key = "0|org.example.chat|9|g:other|10001", groupKey = "0|org.example.chat|g:other", isGroupSummary = false)

        val result = process(chatSummary, active = listOf(chatSummary.asActive(), otherGroup))

        assertEquals(true, (result as PipelineResult.Forward).event.isGroupSummary)
    }

    @Test
    fun `a repost with the same text within 5 seconds is a duplicate`() {
        process(mail)

        assertEquals(PipelineResult.Skip(SkipReason.DUPLICATE), process(mail.copy(postTime = mail.postTime + 4_999)))
    }

    @Test
    fun `a repost with new text within 5 seconds is forwarded`() {
        process(mail)

        val result = process(mail.copy(postTime = mail.postTime + 2_000, text = "Second invoice"))

        assertEquals("Second invoice", (result as PipelineResult.Forward).event.body)
    }

    @Test
    fun `the same text 5 seconds after the last post is forwarded again`() {
        process(mail)

        assertEquals(true, process(mail.copy(postTime = mail.postTime + 5_000)) is PipelineResult.Forward)
    }

    private fun forwarded(posted: PostedNotification) = (process(posted) as PipelineResult.Forward).event

    @Test
    fun `the expanded text wins over the collapsed one`() {
        assertEquals("Your invoice is ready. Total: 40 EUR", forwarded(mail.copy(bigText = "Your invoice is ready. Total: 40 EUR")).body)
    }

    @Test
    fun `a direct chat shows its latest message`() {
        val chat = mail.copy(
            title = "Alice",
            text = "2 new messages",
            conversation = Conversation(
                title = null,
                isGroup = false,
                messages = listOf(Message("Alice", "Hi"), Message("Alice", "Are you there?")),
            ),
        )

        val event = forwarded(chat)

        assertEquals("Alice" to "Are you there?", event.title to event.body)
    }

    @Test
    fun `a group chat is titled by the conversation and names the sender`() {
        val chat = mail.copy(
            title = "Family: Mom",
            conversation = Conversation(
                title = "Family",
                isGroup = true,
                messages = listOf(Message("Dad", "Home soon"), Message("Mom", "Dinner at 7")),
            ),
        )

        val event = forwarded(chat)

        assertEquals("Family" to "Mom: Dinner at 7", event.title to event.body)
    }

    @Test
    fun `an action that takes free text makes the event replyable`() {
        val event = forwarded(mail.copy(actions = listOf(PostedAction("Mark as read", false), PostedAction("Reply", true))))

        assertEquals(true to listOf(EventAction("reply", "Reply", EventActionType.TEXT)), event.replyable to event.actions)
    }

    @Test
    fun `blank texts become null and lone surrogates become replacement characters`() {
        val event = forwarded(mail.copy(title = "  ", text = "broken \uD83D emoji"))

        assertEquals(null to "broken \uFFFD emoji", event.title to event.body)
    }

    private fun PostedNotification.asActive() = ActiveNotification(key, groupKey, isGroupSummary)
}
