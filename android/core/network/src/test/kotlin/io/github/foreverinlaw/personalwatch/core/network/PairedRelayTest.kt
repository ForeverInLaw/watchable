package io.github.foreverinlaw.personalwatch.core.network

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteResponse
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyResult
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.util.concurrent.TimeUnit
import kotlin.time.Duration.Companion.seconds

class PairedRelayTest {
    @get:Rule
    val folder = TemporaryFolder()

    private val server = MockWebServer()

    private val credentials = PairCompleteResponse(
        androidDeviceId = "c99d4f00-ecdc-4d75-879e-473f63bcc9c8",
        androidDeviceToken = "sDxL4rPeYN53lN-rmJIMmRJXVz5Ytnp2uB5P_WCo6CI",
        watchDeviceId = "12861bc2-25be-4ee8-89f4-a568cccacc64",
    )

    private val event = NotificationEvent(
        eventId = "0b6f5f3e-2c1d-4f6a-9e8b-7a6c5d4e3f21",
        sourcePackage = "org.example.mail",
        sourceApp = null,
        notificationKey = "0|org.example.mail|7|null|10001",
        groupKey = null,
        postedAt = "2026-11-25T08:30:00Z",
        title = null,
        body = null,
        subtext = null,
        category = null,
        isOngoing = false,
        isClearable = true,
        isGroupSummary = false,
        replyable = false,
        actions = emptyList(),
    )

    @Before
    fun start() = server.start()

    @After
    fun stop() = server.close()

    /** What Firebase hands the Companion; null as in a build without Firebase. */
    private var fcmToken: String? = null

    private fun TestScope.relay() = PairedRelay(
        client = RelayClient(server.url("/")),
        store = PreferenceDataStoreFactory.create(scope = backgroundScope) { folder.root.resolve("pairing.preferences_pb") },
        fcmToken = { fcmToken },
    )

    private fun respond(code: Int, body: String) = server.enqueue(MockResponse.Builder().code(code).body(body).build())

    private fun pairedBody(paired: PairCompleteResponse = credentials) =
        """{"android_device_id":"${paired.androidDeviceId}",""" +
            """"android_device_token":"${paired.androidDeviceToken}",""" +
            """"watch_device_id":"${paired.watchDeviceId}"}"""

    private fun respondPaired() = respond(201, pairedBody())

    @Test
    fun `pairing keeps the credentials the relay returns`() = runTest {
        val relay = relay()
        respondPaired()

        assertEquals(RelayOutcome.Accepted(credentials), relay.pair(code = "48151623", name = "Pixel 8"))
        assertEquals(credentials, relay.credentials.first())
    }

    @Test
    fun `a pairing the relay accepted is kept even if the caller stops waiting`() = runTest(timeout = 20.seconds) {
        val relay = relay()
        server.enqueue(
            MockResponse.Builder().code(201).body(pairedBody()).headersDelay(300, TimeUnit.MILLISECONDS).build(),
        )

        val pairing = launch { relay.pair(code = "48151623", name = null) }
        // Runs the coroutine up to the network call, which waits on another thread for the answer.
        runCurrent()
        assertNotNull(server.takeRequest(5, TimeUnit.SECONDS))
        pairing.cancelAndJoin()

        assertEquals(credentials, relay.credentials.first())
    }

    @Test
    fun `a later pairing wins even when the earlier answer arrives last`() = runTest(timeout = 20.seconds) {
        val relay = relay()
        val newer = credentials.copy(androidDeviceToken = "N".repeat(43))
        server.enqueue(
            MockResponse.Builder().code(201).body(pairedBody()).headersDelay(500, TimeUnit.MILLISECONDS).build(),
        )
        respond(201, pairedBody(newer))

        val earlier = launch { relay.pair(code = "11111111", name = null) }
        runCurrent()
        assertNotNull(server.takeRequest(5, TimeUnit.SECONDS))
        val later = launch { relay.pair(code = "22222222", name = null) }
        joinAll(earlier, later)

        assertEquals(newer, relay.credentials.first())
    }

    @Test
    fun `a wrong code keeps the Companion unpaired`() = runTest {
        val relay = relay()
        respond(400, """{"error":{"code":"invalid_pairing_code","message":"m","retryable":false}}""")

        assertEquals(RelayOutcome.Rejected(400, "invalid_pairing_code"), relay.pair(code = "00000000", name = null))
        assertNull(relay.credentials.first())
    }

    @Test
    fun `events go out with the token from pairing`() = runTest {
        val relay = relay()
        respondPaired()
        relay.pair(code = "48151623", name = null)
        server.takeRequest()
        respond(202, "")

        assertEquals(RelayOutcome.Accepted(Unit), relay.postNotification(event))
        assertEquals("Bearer ${credentials.androidDeviceToken}", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `a revoked token unpairs the Companion`() = runTest {
        val relay = relay()
        respondPaired()
        relay.pair(code = "48151623", name = null)
        respond(401, """{"error":{"code":"invalid_token","message":"m","retryable":false}}""")

        assertEquals(RelayOutcome.Rejected(401, "invalid_token"), relay.postNotification(event))
        assertNull(relay.credentials.first())
    }

    @Test
    fun `an event is not sent before pairing`() = runTest {
        val relay = relay()

        assertEquals(RelayOutcome.Rejected(401, "invalid_token"), relay.postNotification(event))
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `a reply result goes out with the token from pairing`() = runTest {
        val relay = relay()
        respondPaired()
        relay.pair(code = "48151623", name = null)
        server.takeRequest()
        respond(204, "")

        assertEquals(RelayOutcome.Accepted(Unit), relay.postReplyResult(REPLY_ID, ReplyResult.Sent))
        val request = server.takeRequest()
        assertEquals("/v1/replies/$REPLY_ID/result", request.url.encodedPath)
        assertEquals("Bearer ${credentials.androidDeviceToken}", request.headers["Authorization"])
    }

    @Test
    fun `a reply result refused for a revoked token unpairs the Companion`() = runTest {
        val relay = relay()
        respondPaired()
        relay.pair(code = "48151623", name = null)
        respond(401, """{"error":{"code":"invalid_token","message":"m","retryable":false}}""")

        assertEquals(RelayOutcome.Rejected(401, "invalid_token"), relay.postReplyResult(REPLY_ID, ReplyResult.Sent))
        assertNull(relay.credentials.first())
    }

    @Test
    fun `pairing sends the FCM token`() = runTest {
        val relay = relay()
        fcmToken = "fcm-1"
        respondPaired()

        relay.pair(code = "48151623", name = null)

        assertEquals(
            """{"pairing_code":"48151623","fcm_token":"fcm-1","platform":"android"}""",
            server.takeRequest().body?.utf8(),
        )
    }

    /** Pairs with [fcmToken] and takes the pairing request off the server. */
    private suspend fun PairedRelay.pairWithFcmToken() {
        respondPaired()
        pair(code = "48151623", name = null)
        server.takeRequest()
    }

    @Test
    fun `a new FCM token goes to the relay with the device token`() = runTest {
        val relay = relay()
        fcmToken = "fcm-1"
        relay.pairWithFcmToken()
        respond(204, "")
        fcmToken = "fcm-2"

        assertEquals(RelayOutcome.Accepted(Unit), relay.syncPushToken())
        val request = server.takeRequest()
        assertEquals("/v1/devices/${credentials.androidDeviceId}/push-token", request.url.encodedPath)
        assertEquals("Bearer ${credentials.androidDeviceToken}", request.headers["Authorization"])
        assertEquals("""{"push_token":"fcm-2"}""", request.body?.utf8())
    }

    @Test
    fun `the FCM token sent in pairing is not sent again`() = runTest {
        val relay = relay()
        fcmToken = "fcm-1"
        relay.pairWithFcmToken()

        assertEquals(RelayOutcome.Accepted(Unit), relay.syncPushToken())
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `an FCM token the relay took is not sent again`() = runTest {
        val relay = relay()
        relay.pairWithFcmToken()
        respond(204, "")
        fcmToken = "fcm-2"
        relay.syncPushToken()

        assertEquals(RelayOutcome.Accepted(Unit), relay.syncPushToken())
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `an FCM token the relay did not take is sent again`() = runTest {
        val relay = relay()
        relay.pairWithFcmToken()
        respond(503, """{"error":{"code":"internal_error","message":"m","retryable":true}}""")
        respond(204, "")
        fcmToken = "fcm-1"

        assertEquals(RelayOutcome.Retry(after = null), relay.syncPushToken())
        assertEquals(RelayOutcome.Accepted(Unit), relay.syncPushToken())
        assertEquals(3, server.requestCount)
    }

    @Test
    fun `an FCM token is not sent before pairing`() = runTest {
        val relay = relay()
        fcmToken = "fcm-1"

        assertEquals(RelayOutcome.Rejected(401, "invalid_token"), relay.syncPushToken())
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `token updates that overlap leave the relay with the current FCM token`() = runTest {
        val relay = relay()
        relay.pairWithFcmToken()
        respond(204, "")
        // Firebase refreshed the token after an update for the old one had been started.
        fcmToken = "fcm-2"

        listOf(launch { relay.syncPushToken() }, launch { relay.syncPushToken() }).joinAll()
        assertEquals("""{"push_token":"fcm-2"}""", server.takeRequest().body?.utf8())
        assertEquals(2, server.requestCount)
    }

    private companion object {
        const val REPLY_ID = "4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60"
    }
}
