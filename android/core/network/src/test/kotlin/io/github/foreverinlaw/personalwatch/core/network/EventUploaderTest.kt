package io.github.foreverinlaw.personalwatch.core.network

import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.time.Duration.Companion.seconds

class EventUploaderTest {
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

    /** Answers with [outcomes] in turn, repeating the last one, and records when each send happened. */
    private class FakeRelay(private val scope: TestScope, vararg outcomes: RelayOutcome) {
        private val remaining = ArrayDeque(outcomes.toList())
        val sentAt = mutableListOf<Long>()

        suspend fun send(event: NotificationEvent): RelayOutcome {
            sentAt += scope.currentTime
            return if (remaining.size > 1) remaining.removeFirst() else remaining.first()
        }
    }

    private fun TestScope.upload(relay: FakeRelay): MutableList<RelayOutcome> {
        val finished = mutableListOf<RelayOutcome>()
        // The upper jitter bound, so the delays are predictable.
        EventUploader(this, relay::send, jitter = { it }, onFinished = { _, outcome -> finished += outcome }).upload(event)
        advanceUntilIdle()
        return finished
    }

    @Test
    fun `a retryable failure is retried with growing delays until accepted`() = runTest {
        val relay = FakeRelay(this, RelayOutcome.Retry(null), RelayOutcome.Retry(null), RelayOutcome.Accepted)

        assertEquals(listOf(RelayOutcome.Accepted), upload(relay))
        assertEquals(listOf(0L, 1_000L, 3_000L), relay.sentAt)
    }

    @Test
    fun `the delay the relay asks for wins over the backoff`() = runTest {
        val relay = FakeRelay(this, RelayOutcome.Retry(30.seconds), RelayOutcome.Accepted)

        upload(relay)

        assertEquals(listOf(0L, 30_000L), relay.sentAt)
    }

    @Test
    fun `a rejected event is not retried`() = runTest {
        val rejected = RelayOutcome.Rejected(400, "invalid_request")
        val relay = FakeRelay(this, rejected)

        assertEquals(listOf<RelayOutcome>(rejected), upload(relay))
        assertEquals(1, relay.sentAt.size)
    }

    @Test
    fun `delays stop growing at 5 minutes and the uploader gives up after 12 attempts`() = runTest {
        val relay = FakeRelay(this, RelayOutcome.Retry(null))

        assertEquals(listOf<RelayOutcome>(RelayOutcome.Retry(null)), upload(relay))
        assertEquals(
            listOf(1L, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300).map { it * 1_000 },
            relay.sentAt.zipWithNext { a, b -> b - a },
        )
    }
}
