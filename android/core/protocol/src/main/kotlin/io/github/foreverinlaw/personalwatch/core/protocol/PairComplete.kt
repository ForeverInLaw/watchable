package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Body of `POST /v1/pair/complete` (TZ F1, protocol/schema/pair-complete-request.schema.json).
 * A null [name] or [fcmToken] is left out, as the schema has no null for them.
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class PairCompleteRequest(
    /** The 8 digits the watch shows. */
    @SerialName("pairing_code") val pairingCode: String,
    val name: String? = null,
    /** Where the relay sends replies; null when Firebase is not configured or has no token yet. */
    @SerialName("fcm_token") val fcmToken: String? = null,
) {
    @EncodeDefault
    val platform: String = "android"
}

/** 201 answer to `POST /v1/pair/complete` (protocol/schema/pair-complete-response.schema.json). */
@Serializable
data class PairCompleteResponse(
    @SerialName("android_device_id") val androidDeviceId: String,
    /** Bearer token for every later request of the Companion. */
    @SerialName("android_device_token") val androidDeviceToken: String,
    @SerialName("watch_device_id") val watchDeviceId: String,
)

/** Body of `POST /v1/devices/{id}/push-token` (protocol/schema/push-token-request.schema.json): the new FCM token. */
@Serializable
data class PushTokenRequest(@SerialName("push_token") val pushToken: String)
