package io.github.foreverinlaw.personalwatch.core.network

import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteRequest
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteResponse
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyFailure
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyResult
import org.junit.Assert.assertNull
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit
import kotlin.time.Duration.Companion.seconds

class RelayClientTest {
    private val server = MockWebServer()
    private lateinit var client: RelayClient

    private val event = NotificationEvent(
        eventId = "0b6f5f3e-2c1d-4f6a-9e8b-7a6c5d4e3f21",
        sourcePackage = "org.example.mail",
        sourceApp = "Mail",
        notificationKey = "0|org.example.mail|7|null|10001",
        groupKey = null,
        postedAt = "2026-11-25T08:30:00.250Z",
        title = "Invoice",
        body = "Your invoice is ready",
        subtext = null,
        category = "email",
        isOngoing = false,
        isClearable = true,
        isGroupSummary = false,
        replyable = false,
        actions = emptyList(),
    )

    @Before
    fun start() {
        server.start()
        client = RelayClient(baseUrl = server.url("/"), replyResultTimeout = 1.seconds)
    }

    @After
    fun stop() = server.close()

    private fun respond(code: Int, body: String = "", vararg headers: Pair<String, String>) {
        val response = MockResponse.Builder().code(code).body(body)
        headers.forEach { (name, value) -> response.addHeader(name, value) }
        server.enqueue(response.build())
    }

    private fun error(code: String, retryable: Boolean) =
        """{"error":{"code":"$code","message":"m","retryable":$retryable}}"""

    @Test
    fun `posts the event with the device token and its id as the idempotency key`() = runTest {
        respond(202)

        assertEquals(RelayOutcome.Accepted(Unit), client.postNotification(TOKEN, event))

        val request = server.takeRequest()
        assertEquals("POST /v1/events/notification", "${request.method} ${request.url.encodedPath}")
        assertEquals("Bearer $TOKEN", request.headers["Authorization"])
        assertEquals(event.eventId, request.headers["Idempotency-Key"])
        assertEquals(true, request.headers["Content-Type"]?.startsWith("application/json"))
        assertEquals(true, request.body?.utf8()?.contains("\"event_id\":\"${event.eventId}\""))
    }

    @Test
    fun `a duplicate counts as accepted`() = runTest {
        respond(409, error("duplicate", retryable = false))

        assertEquals(RelayOutcome.Accepted(Unit), client.postNotification(TOKEN, event))
    }

    @Test
    fun `a retryable server error is retried and a final one is rejected`() = runTest {
        respond(503, error("apns_unavailable", retryable = true))
        respond(500, error("apns_rejected", retryable = false))

        assertEquals(RelayOutcome.Retry(after = null), client.postNotification(TOKEN, event))
        assertEquals(RelayOutcome.Rejected(500, "apns_rejected"), client.postNotification(TOKEN, event))
    }

    @Test
    fun `rate limiting is retried after the time the relay asks for`() = runTest {
        respond(429, error("rate_limited", retryable = true), "Retry-After" to "30")

        assertEquals(RelayOutcome.Retry(after = 30.seconds), client.postNotification(TOKEN, event))
    }

    @Test
    fun `a gateway error without a protocol body is retried`() = runTest {
        respond(502, "<html>Bad gateway</html>")

        assertEquals(RelayOutcome.Retry(after = null), client.postNotification(TOKEN, event))
    }

    @Test
    fun `an invalid token is rejected`() = runTest {
        respond(401, error("invalid_token", retryable = false))

        assertEquals(RelayOutcome.Rejected(401, "invalid_token"), client.postNotification(TOKEN, event))
    }

    @Test
    fun `an unreachable relay is retried`() = runTest {
        server.close()

        assertEquals(RelayOutcome.Retry(after = null), client.postNotification(TOKEN, event))
    }

    @Test
    fun `completes pairing without a bearer token and returns the Companion's credentials`() = runTest {
        respond(
            201,
            """{"android_device_id":"c99d4f00-ecdc-4d75-879e-473f63bcc9c8",""" +
                """"android_device_token":"sDxL4rPeYN53lN-rmJIMmRJXVz5Ytnp2uB5P_WCo6CI",""" +
                """"watch_device_id":"12861bc2-25be-4ee8-89f4-a568cccacc64"}""",
        )

        val outcome = client.completePairing(PairCompleteRequest(pairingCode = "48151623", name = "Pixel 8"))

        assertEquals(
            RelayOutcome.Accepted(
                PairCompleteResponse(
                    androidDeviceId = "c99d4f00-ecdc-4d75-879e-473f63bcc9c8",
                    androidDeviceToken = "sDxL4rPeYN53lN-rmJIMmRJXVz5Ytnp2uB5P_WCo6CI",
                    watchDeviceId = "12861bc2-25be-4ee8-89f4-a568cccacc64",
                ),
            ),
            outcome,
        )
        val request = server.takeRequest()
        assertEquals("POST /v1/pair/complete", "${request.method} ${request.url.encodedPath}")
        assertNull(request.headers["Authorization"])
        assertEquals("""{"pairing_code":"48151623","name":"Pixel 8","platform":"android"}""", request.body?.utf8())
    }

    @Test
    fun `a wrong pairing code is rejected with its reason`() = runTest {
        respond(400, error("invalid_pairing_code", retryable = false))

        assertEquals(
            RelayOutcome.Rejected(400, "invalid_pairing_code"),
            client.completePairing(PairCompleteRequest(pairingCode = "00000000")),
        )
    }

    @Test
    fun `posts a reply result with the device token and the reply id as the idempotency key`() = runTest {
        respond(204)

        val outcome = client.postReplyResult(TOKEN, REPLY_ID, ReplyResult.Failed(ReplyFailure.NOTIFICATION_GONE))

        assertEquals(RelayOutcome.Accepted(Unit), outcome)
        val request = server.takeRequest()
        assertEquals("POST /v1/replies/$REPLY_ID/result", "${request.method} ${request.url.encodedPath}")
        assertEquals("Bearer $TOKEN", request.headers["Authorization"])
        assertEquals(REPLY_ID, request.headers["Idempotency-Key"])
        assertEquals("""{"status":"failed","error":"notification_gone"}""", request.body?.utf8())
    }

    @Test
    fun `a reply result the relay already has counts as accepted`() = runTest {
        respond(409, error("duplicate", retryable = false))

        assertEquals(RelayOutcome.Accepted(Unit), client.postReplyResult(TOKEN, REPLY_ID, ReplyResult.Sent))
    }

    @Test
    fun `a reply result the relay does not answer in time is given up for a retry`() = runTest {
        server.enqueue(MockResponse.Builder().code(204).headersDelay(5, TimeUnit.SECONDS).build())

        assertEquals(RelayOutcome.Retry(after = null), client.postReplyResult(TOKEN, REPLY_ID, ReplyResult.Sent))
    }

    private companion object {
        const val REPLY_ID = "4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60"
        const val TOKEN = "sDxL4rPeYN53lN-rmJIMmRJXVz5Ytnp2uB5P_WCo6CI"
    }
}
