package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonClassDiscriminator

/**
 * Body of `POST /v1/replies/{reply_id}/result` (TZ §5.6, protocol/schema/reply-result.schema.json):
 * what the Companion made of `reply.execute`. Encode it as [ReplyResult], not as a subtype, so the
 * `status` discriminator is written.
 */
@OptIn(ExperimentalSerializationApi::class)
@JsonClassDiscriminator("status")
@Serializable
sealed interface ReplyResult {
    /** `actionIntent.send()` went through. */
    @Serializable
    @SerialName("sent")
    data object Sent : ReplyResult

    @Serializable
    @SerialName("failed")
    data class Failed(val error: ReplyFailure) : ReplyResult
}

/** Why the Companion could not send a reply (TZ §7.4). */
@Serializable
enum class ReplyFailure {
    /** The notification has left the shade, or the notification listener is not connected. */
    @SerialName("notification_gone")
    NOTIFICATION_GONE,

    /** No action of the notification takes free text. */
    @SerialName("remote_input_unsupported")
    REMOTE_INPUT_UNSUPPORTED,
}
