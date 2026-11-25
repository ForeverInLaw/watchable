package io.github.foreverinlaw.personalwatch.companion

import android.app.Notification
import android.app.PendingIntent
import android.app.RemoteInput
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.notification.StatusBarNotification
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyExecute
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyFailure
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyResult

/**
 * Sends a reply from the watch through the reply action of the notification it answers, as if the
 * user had typed it in the shade (TZ §7.4). [activeNotification] finds a notification still in the
 * shade by its key, and finds none while the notification listener is not connected.
 */
class ReplyCommandHandler(
    private val context: Context,
    private val activeNotification: (key: String) -> StatusBarNotification?,
) {
    fun execute(reply: ReplyExecute): ReplyResult {
        val sbn = activeNotification(reply.notificationKey) ?: return GONE
        val (action, input) = sbn.notification.actions.orEmpty()
            .firstNotNullOfOrNull { action -> action.freeTextInput()?.let { action to it } }
            ?: return ReplyResult.Failed(ReplyFailure.REMOTE_INPUT_UNSUPPORTED)
        val fillIn = Intent()
        RemoteInput.addResultsToIntent(action.remoteInputs, fillIn, Bundle().apply { putCharSequence(input.resultKey, reply.text) })
        RemoteInput.setResultsSource(fillIn, RemoteInput.SOURCE_FREE_FORM_INPUT)
        return try {
            action.actionIntent.send(context, 0, fillIn)
            ReplyResult.Sent
        } catch (_: PendingIntent.CanceledException) {
            // The app withdrew the action, as it does once the notification is dismissed.
            GONE
        }
    }

    private companion object {
        val GONE = ReplyResult.Failed(ReplyFailure.NOTIFICATION_GONE)
    }
}

/** The input of this action that takes typed or dictated text, if any. */
fun Notification.Action.freeTextInput(): RemoteInput? = remoteInputs.orEmpty().firstOrNull { it.allowFreeFormInput }
