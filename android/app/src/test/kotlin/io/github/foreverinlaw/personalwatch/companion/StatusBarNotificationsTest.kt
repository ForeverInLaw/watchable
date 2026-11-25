package io.github.foreverinlaw.personalwatch.companion

import android.app.Notification
import android.app.Person
import android.app.RemoteInput
import android.app.PendingIntent
import android.content.Intent
import android.os.Process
import android.service.notification.StatusBarNotification
import io.github.foreverinlaw.personalwatch.core.notifications.Conversation
import io.github.foreverinlaw.personalwatch.core.notifications.Message
import io.github.foreverinlaw.personalwatch.core.notifications.PostedAction
import io.github.foreverinlaw.personalwatch.core.notifications.PostedNotification
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

@RunWith(RobolectricTestRunner::class)
class StatusBarNotificationsTest {
    private val context = RuntimeEnvironment.getApplication()

    @Test
    fun `a group chat notification is copied with its messages and reply action`() {
        val reply = Notification.Action.Builder(
            null,
            "Reply",
            PendingIntent.getBroadcast(context, 0, Intent("reply"), PendingIntent.FLAG_MUTABLE),
        ).addRemoteInput(RemoteInput.Builder("text").build()).build()
        val markRead = Notification.Action.Builder(
            null,
            "Mark as read",
            PendingIntent.getBroadcast(context, 1, Intent("read"), PendingIntent.FLAG_IMMUTABLE),
        ).build()
        val notification = Notification.Builder(context, "chats")
            .setContentTitle("Family: Mom")
            .setContentText("Dinner at 7")
            .setSubText("work")
            .setCategory(Notification.CATEGORY_MESSAGE)
            .setGroup("chats")
            .setStyle(
                Notification.MessagingStyle(Person.Builder().setName("Me").build())
                    .setConversationTitle("Family")
                    .setGroupConversation(true)
                    .addMessage("Home soon", 1_000, Person.Builder().setName("Dad").build())
                    .addMessage("Dinner at 7", 2_000, Person.Builder().setName("Mom").build()),
            )
            .addAction(markRead)
            .addAction(reply)
            .build()
        val sbn = StatusBarNotification(
            "org.example.chat", "org.example.chat", 5, null, 10001, 0, 0,
            notification, Process.myUserHandle(), 1_795_595_400_250,
        )

        assertEquals(
            PostedNotification(
                key = sbn.key,
                packageName = "org.example.chat",
                appLabel = "Chat",
                groupKey = sbn.groupKey,
                postTime = 1_795_595_400_250,
                category = "msg",
                isOngoing = false,
                isClearable = true,
                isGroupSummary = false,
                title = "Family: Mom",
                text = "Dinner at 7",
                bigText = null,
                subText = "work",
                conversation = Conversation(
                    title = "Family",
                    isGroup = true,
                    messages = listOf(Message("Dad", "Home soon"), Message("Mom", "Dinner at 7")),
                ),
                actions = listOf(PostedAction("Mark as read", acceptsFreeText = false), PostedAction("Reply", acceptsFreeText = true)),
            ),
            sbn.toPostedNotification(appLabel = "Chat"),
        )
    }

    @Test
    fun `an ungrouped notification has no group key`() {
        val notification = Notification.Builder(context, "mail").setContentTitle("Invoice").build()
        val sbn = StatusBarNotification(
            "org.example.mail", "org.example.mail", 7, null, 10001, 0, 0,
            notification, Process.myUserHandle(), 0,
        )

        assertEquals(null, sbn.toPostedNotification(appLabel = null).groupKey)
    }

    @Test
    fun `messages by the MessagingStyle user are marked as the user's own`() {
        val me = Person.Builder().setName("Me").build()
        val notification = Notification.Builder(context, "chats")
            .setStyle(
                Notification.MessagingStyle(me)
                    .addMessage("Home soon", 1_000, Person.Builder().setName("Dad").build())
                    .addMessage("On my way", 2_000, null as Person?)
                    .addMessage("See you", 3_000, me),
            )
            .build()
        val sbn = StatusBarNotification(
            "org.example.chat", "org.example.chat", 5, null, 10001, 0, 0,
            notification, Process.myUserHandle(), 0,
        )

        assertEquals(
            listOf(false, true, true),
            sbn.toPostedNotification(appLabel = null).conversation?.messages?.map { it.isFromUser },
        )
    }
}
