package io.github.foreverinlaw.personalwatch.core.network

import io.github.foreverinlaw.personalwatch.core.protocol.ErrorResponse
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import io.github.foreverinlaw.personalwatch.core.protocol.ProtocolJson
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

/**
 * The relay's HTTP API (TZ §5.1). Until pairing (M2) every request carries one static bearer token.
 */
class RelayClient(
    baseUrl: HttpUrl,
    private val token: String,
    private val http: OkHttpClient = OkHttpClient(),
) {
    private val notificationUrl = baseUrl.newBuilder().addPathSegments("v1/events/notification").build()

    /** Sends one event; the event id doubles as the idempotency key, so a resend is recognized. */
    suspend fun postNotification(event: NotificationEvent): RelayOutcome {
        val request = Request.Builder()
            .url(notificationUrl)
            .header("Authorization", "Bearer $token")
            .header("Idempotency-Key", event.eventId)
            .post(ProtocolJson.encodeToString(event).toRequestBody(JSON))
            .build()
        return try {
            withContext(Dispatchers.IO) { http.newCall(request).execute().use(::outcomeOf) }
        } catch (_: IOException) {
            RelayOutcome.Retry(after = null)
        }
    }

    /** TZ §5.10: a duplicate means the relay already has the event. */
    private fun outcomeOf(response: Response): RelayOutcome {
        if (response.isSuccessful || response.code == HTTP_CONFLICT) return RelayOutcome.Accepted
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

/** What the relay made of a request. */
sealed interface RelayOutcome {
    /** Stored, or already stored by an earlier attempt. */
    data object Accepted : RelayOutcome

    /** Sending the same request again can succeed; [after] is the delay the relay asked for. */
    data class Retry(val after: Duration?) : RelayOutcome

    /** Sending it again will not help. */
    data class Rejected(val status: Int, val code: String?) : RelayOutcome
}
