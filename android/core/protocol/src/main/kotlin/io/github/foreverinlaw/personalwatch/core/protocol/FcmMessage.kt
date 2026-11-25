package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** A message the relay sends the Companion over FCM, decoded from its envelope (TZ §5.3, §9.4). */
sealed interface FcmMessage {
    /** The envelope id; the same message sent again keeps it. */
    val id: String

    /** `reply.execute`: send [payload]'s text through the notification's reply action (TZ §5.6, §7.4). */
    data class Reply(override val id: String, val payload: ReplyExecute) : FcmMessage

    companion object {
        /**
         * Reads FCM `data` (protocol/schema/fcm-envelope.schema.json). Null for a message this build
         * cannot act on: another protocol version, an unknown type or a malformed envelope or payload.
         */
        fun decode(data: Map<String, String>): FcmMessage? = try {
            val envelope = ProtocolJson.decodeFromJsonElement(Envelope.serializer(), JsonObject(data.mapValues { JsonPrimitive(it.value) }))
            when {
                envelope.v != VERSION -> null
                envelope.type == REPLY_EXECUTE -> Reply(envelope.id, ProtocolJson.decodeFromString(envelope.payload))
                else -> null
            }
        } catch (_: SerializationException) {
            null
        } catch (_: IllegalArgumentException) {
            null
        }

        private const val VERSION = "1"
        private const val REPLY_EXECUTE = "reply.execute"
    }
}

/** The envelope as FCM data carries it: every value a string, [payload] the JSON text of the body. */
@Serializable
private data class Envelope(
    val v: String,
    val id: String,
    val type: String,
    @SerialName("sent_at") val sentAt: String,
    @SerialName("device_id") val deviceId: String,
    val payload: String,
)

/** Payload of `reply.execute` (protocol/schema/reply-execute.schema.json). */
@Serializable
data class ReplyExecute(
    @SerialName("reply_id") val replyId: String,
    @SerialName("event_id") val eventId: String,
    /** The `StatusBarNotification` key the reply goes to. */
    @SerialName("notification_key") val notificationKey: String,
    @SerialName("source_package") val sourcePackage: String,
    val text: String,
)
