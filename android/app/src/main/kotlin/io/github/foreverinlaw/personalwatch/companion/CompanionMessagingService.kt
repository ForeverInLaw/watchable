package io.github.foreverinlaw.personalwatch.companion

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import io.github.foreverinlaw.personalwatch.core.protocol.FcmMessage
import kotlinx.coroutines.runBlocking

/** Receives the relay's FCM messages and FCM token changes; runs only when Firebase is configured (TZ §7.5). */
class CompanionMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        (application as CompanionApp).updateFcmToken(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        when (val received = FcmMessage.decode(message.data)) {
            is FcmMessage.Reply -> reply(received)
            null -> Log.w(TAG, "ignored FCM message ${message.messageId}")
        }
    }

    /**
     * Sends the reply and reports the result before returning: the system may stop the process
     * soon after, and the result request gives up after 10 seconds (TZ §7.4). Runs on FCM's own
     * background thread, so blocking it holds up nothing else.
     */
    private fun reply(message: FcmMessage.Reply) {
        val handled = (application as CompanionApp).replies?.let { replies -> runBlocking { replies.receive(message) } }
        // Null for a message already run, or a build without a relay. Never log the reply text (TZ §7.8).
        Log.i(TAG, "reply ${message.payload.replyId}: ${handled ?: "dropped"}")
    }

    private companion object {
        const val TAG = "CompanionMessaging"
    }
}
