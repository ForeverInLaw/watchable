package io.github.foreverinlaw.personalwatch.core.network

import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
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
        client = RelayClient(baseUrl = server.url("/"), token = "static-token")
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
    fun `posts the event with the bearer token and its id as the idempotency key`() = runTest {
        respond(202)

        assertEquals(RelayOutcome.Accepted, client.postNotification(event))

        val request = server.takeRequest()
        assertEquals("POST /v1/events/notification", "${request.method} ${request.url.encodedPath}")
        assertEquals("Bearer static-token", request.headers["Authorization"])
        assertEquals(event.eventId, request.headers["Idempotency-Key"])
        assertEquals(true, request.headers["Content-Type"]?.startsWith("application/json"))
        assertEquals(true, request.body?.utf8()?.contains("\"event_id\":\"${event.eventId}\""))
    }

    @Test
    fun `a duplicate counts as accepted`() = runTest {
        respond(409, error("duplicate", retryable = false))

        assertEquals(RelayOutcome.Accepted, client.postNotification(event))
    }

    @Test
    fun `a retryable server error is retried and a final one is rejected`() = runTest {
        respond(503, error("apns_unavailable", retryable = true))
        respond(500, error("apns_rejected", retryable = false))

        assertEquals(RelayOutcome.Retry(after = null), client.postNotification(event))
        assertEquals(RelayOutcome.Rejected(500, "apns_rejected"), client.postNotification(event))
    }

    @Test
    fun `rate limiting is retried after the time the relay asks for`() = runTest {
        respond(429, error("rate_limited", retryable = true), "Retry-After" to "30")

        assertEquals(RelayOutcome.Retry(after = 30.seconds), client.postNotification(event))
    }

    @Test
    fun `a gateway error without a protocol body is retried`() = runTest {
        respond(502, "<html>Bad gateway</html>")

        assertEquals(RelayOutcome.Retry(after = null), client.postNotification(event))
    }

    @Test
    fun `an invalid token is rejected`() = runTest {
        respond(401, error("invalid_token", retryable = false))

        assertEquals(RelayOutcome.Rejected(401, "invalid_token"), client.postNotification(event))
    }

    @Test
    fun `an unreachable relay is retried`() = runTest {
        server.close()

        assertEquals(RelayOutcome.Retry(after = null), client.postNotification(event))
    }
}
