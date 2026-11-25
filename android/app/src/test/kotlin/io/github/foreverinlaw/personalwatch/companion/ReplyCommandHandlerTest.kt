package io.github.foreverinlaw.personalwatch.companion

import android.app.Notification
import android.app.PendingIntent
import android.app.RemoteInput
import android.content.Intent
import android.os.Process
import android.service.notification.StatusBarNotification
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyExecute
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf

@RunWith(RobolectricTestRunner::class)
class ReplyCommandHandlerTest {
    private val context = RuntimeEnvironment.getApplication()

    private fun action(title: String, intentAction: String, vararg inputs: RemoteInput): Notification.Action {
        val intent = PendingIntent.getBroadcast(context, 0, Intent(intentAction), PendingIntent.FLAG_MUTABLE)
        return Notification.Action.Builder(null, title, intent).apply { inputs.forEach(::addRemoteInput) }.build()
    }

    private fun posted(vararg actions: Notification.Action): StatusBarNotification {
        val notification = Notification.Builder(context, "chats").setContentTitle("Alice").apply { actions.forEach(::addAction) }.build()
        return StatusBarNotification(
            "com.whatsapp", "com.whatsapp", 1234, null, 10001, 0, 0,
            notification, Process.myUserHandle(), 1_795_595_400_250,
        )
    }

    private fun reply(key: String) = ReplyExecute(
        replyId = "4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60",
        eventId = "018f3a5e-7c2b-7d4e-9a1b-3c5d7e9f1a2b",
        notificationKey = key,
        sourcePackage = "com.whatsapp",
        text = "Ок",
    )

    private fun handler(vararg shade: StatusBarNotification) =
        ReplyCommandHandler(context) { key -> shade.firstOrNull { it.key == key } }

    private fun sentBroadcasts(): List<Intent> = shadowOf(context).broadcastIntents

    @Test
    fun `the text goes through the action that takes free text`() {
        val quickReplies = RemoteInput.Builder("choice").setChoices(arrayOf("Yes", "No")).setAllowFreeFormInput(false).build()
        val sbn = posted(
            action("Mark as read", "read"),
            action("Quick reply", "quick", quickReplies),
            action("Reply", "reply", RemoteInput.Builder("reply_text").build()),
        )

        val outcome = handler(sbn).execute(reply(sbn.key))

        assertEquals(ReplyOutcome.SENT, outcome)
        val sent = sentBroadcasts().single()
        assertEquals("reply", sent.action)
        assertEquals("Ок", RemoteInput.getResultsFromIntent(sent)?.getCharSequence("reply_text")?.toString())
        assertEquals(RemoteInput.SOURCE_FREE_FORM_INPUT, RemoteInput.getResultsSource(sent))
    }

    @Test
    fun `a notification that is no longer in the shade is gone`() {
        val sbn = posted(action("Reply", "reply", RemoteInput.Builder("reply_text").build()))

        val outcome = handler(sbn).execute(reply("0|com.whatsapp|999|null|10001"))

        assertEquals(ReplyOutcome.NOTIFICATION_GONE, outcome)
        assertEquals(emptyList<Intent>(), sentBroadcasts())
    }

    @Test
    fun `a notification without a free text action cannot take the reply`() {
        val quickReplies = RemoteInput.Builder("choice").setChoices(arrayOf("Yes", "No")).setAllowFreeFormInput(false).build()
        val sbn = posted(action("Mark as read", "read"), action("Quick reply", "quick", quickReplies))

        val outcome = handler(sbn).execute(reply(sbn.key))

        assertEquals(ReplyOutcome.REMOTE_INPUT_UNSUPPORTED, outcome)
        assertEquals(emptyList<Intent>(), sentBroadcasts())
    }
}
