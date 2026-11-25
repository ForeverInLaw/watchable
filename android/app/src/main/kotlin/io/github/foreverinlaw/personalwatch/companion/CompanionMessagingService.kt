package io.github.foreverinlaw.personalwatch.companion

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import io.github.foreverinlaw.personalwatch.core.protocol.FcmMessage

/** Receives the relay's FCM messages and FCM token changes; runs only when Firebase is configured (TZ §7.5). */
class CompanionMessagingService : FirebaseMessagingService() {
    private val app get() = application as CompanionApp

    override fun onNewToken(token: String) {
        app.updateFcmToken(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        when (val received = FcmMessage.decode(message.data)) {
            // Never log the reply text (TZ §7.8).
            is FcmMessage.Reply -> Log.i(TAG, "reply ${received.payload.replyId}: ${app.replies.execute(received.payload)}")
            null -> Log.w(TAG, "ignored FCM message ${message.messageId}")
        }
    }

    private companion object {
        const val TAG = "CompanionMessaging"
    }
}
