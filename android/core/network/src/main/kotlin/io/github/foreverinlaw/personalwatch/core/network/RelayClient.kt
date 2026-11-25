package io.github.foreverinlaw.personalwatch.core.network

import io.github.foreverinlaw.personalwatch.core.protocol.ErrorResponse
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteRequest
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteResponse
import io.github.foreverinlaw.personalwatch.core.protocol.ProtocolJson
import io.github.foreverinlaw.personalwatch.core.protocol.PushTokenRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/** The relay's HTTP API (TZ §5.1); outcomes follow the retry rules of §5.10. */
class RelayClient(private val baseUrl: HttpUrl) {
    private val http = OkHttpClient()
    private val notificationUrl = baseUrl.newBuilder().addPathSegments("v1/events/notification").build()
    private val pairCompleteUrl = baseUrl.newBuilder().addPathSegments("v1/pair/complete").build()

    /**
     * Sends one event with the Companion's device [token]; the event id doubles as the idempotency
     * key, so a resend is recognized, and a duplicate means the relay already has the event.
     */
    suspend fun postNotification(token: String, event: NotificationEvent): RelayOutcome<Unit> {
        val request = Request.Builder()
            .url(notificationUrl)
            .header("Authorization", "Bearer $token")
            .header("Idempotency-Key", event.eventId)
            .post(ProtocolJson.encodeToString(event).toRequestBody(JSON))
            .build()
        return when (val outcome = exchange(request) {}) {
            is RelayOutcome.Rejected if outcome.status == HTTP_CONFLICT -> RelayOutcome.Accepted(Unit)
            else -> outcome
        }
    }

    /** Pairs with the watch showing the code; no bearer token, the code is the proof (TZ F1). */
    suspend fun completePairing(body: PairCompleteRequest): RelayOutcome<PairCompleteResponse> {
        val request = Request.Builder()
            .url(pairCompleteUrl)
            .post(ProtocolJson.encodeToString(body).toRequestBody(JSON))
            .build()
        return exchange(request) { ProtocolJson.decodeFromString<PairCompleteResponse>(it) }
    }

    /** Replaces the FCM token of device [deviceId], the Companion that holds [token] (TZ §5.2). */
    suspend fun updatePushToken(token: String, deviceId: String, body: PushTokenRequest): RelayOutcome<Unit> {
        val url = baseUrl.newBuilder().addPathSegments("v1/devices").addPathSegment(deviceId).addPathSegment("push-token").build()
        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $token")
            .post(ProtocolJson.encodeToString(body).toRequestBody(JSON))
            .build()
        return exchange(request) {}
    }

    /** Runs [request] and decodes a successful body with [decode]; a malformed one is rejected. */
    private suspend fun <T> exchange(request: Request, decode: (String) -> T): RelayOutcome<T> = try {
        withContext(Dispatchers.IO) {
            http.newCall(request).execute().use { response ->
                if (response.isSuccessful) accepted(response, decode) else failure(response)
            }
        }
    } catch (_: IOException) {
        RelayOutcome.Retry(after = null)
    }

    private fun <T> accepted(response: Response, decode: (String) -> T): RelayOutcome<T> = try {
        RelayOutcome.Accepted(decode(response.body.string()))
    } catch (_: SerializationException) {
        RelayOutcome.Rejected(response.code, code = null)
    }

    private fun failure(response: Response): RelayOutcome<Nothing> {
        if (response.code == HTTP_TOO_MANY_REQUESTS) {
            return RelayOutcome.Retry(after = response.header("Retry-After")?.toLongOrNull()?.seconds)
        }
        val error = response.body.string().let { body ->
            try {
                ProtocolJson.decodeFromString<ErrorResponse>(body).error
            } catch (_: SerializationException) {
                null
            }
        }
        return when {
            error?.retryable == true -> RelayOutcome.Retry(after = null)
            // A 5xx without the protocol body comes from the tunnel or proxy in front of the relay.
            error == null && response.code >= HTTP_SERVER_ERROR -> RelayOutcome.Retry(after = null)
            else -> RelayOutcome.Rejected(response.code, error?.code)
        }
    }

    private companion object {
        val JSON = "application/json".toMediaType()
        const val HTTP_CONFLICT = 409
        const val HTTP_TOO_MANY_REQUESTS = 429
        const val HTTP_SERVER_ERROR = 500
    }
}

/** What the relay made of a request; [T] is the body of a successful answer. */
sealed interface RelayOutcome<out T> {
    /** Done, or already done by an earlier attempt. */
    data class Accepted<T>(val body: T) : RelayOutcome<T>

    /** Sending the same request again can succeed; [after] is the delay the relay asked for. */
    data class Retry(val after: Duration?) : RelayOutcome<Nothing>

    /** Sending it again will not help; [code] is the protocol error code, if the relay sent one. */
    data class Rejected(val status: Int, val code: String?) : RelayOutcome<Nothing>
}
