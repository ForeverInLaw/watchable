package io.github.foreverinlaw.personalwatch.core.network

import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.time.Duration.Companion.hours
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
        val sentIds = mutableListOf<String>()

        suspend fun send(event: NotificationEvent): RelayOutcome {
            sentAt += scope.currentTime
            sentIds += event.eventId
            return if (remaining.size > 1) remaining.removeFirst() else remaining.first()
        }
    }

    /** Uploads [events] in order and returns each finished event id with its last outcome. */
    private fun TestScope.upload(relay: FakeRelay, vararg events: NotificationEvent = arrayOf(event)): List<Pair<String, RelayOutcome>> {
        val finished = mutableListOf<Pair<String, RelayOutcome>>()
        // The upper jitter bound, so the delays are predictable; the uploader's queue outlives the test.
        val uploader = EventUploader(backgroundScope, relay::send, jitter = { it }, onFinished = { e, outcome -> finished += e.eventId to outcome })
        events.forEach(uploader::upload)
        // advanceUntilIdle ignores background work; this outlasts every retry schedule here.
        advanceTimeBy(2.hours)
        return finished
    }

    @Test
    fun `a later event waits until the earlier one is finished`() = runTest {
        val later = event.copy(eventId = "later")
        val relay = FakeRelay(this, RelayOutcome.Retry(null), RelayOutcome.Accepted)

        val finished = upload(relay, event, later)

        assertEquals(listOf(event.eventId, event.eventId, "later"), relay.sentIds)
        assertEquals(listOf(event.eventId, "later"), finished.map { it.first })
    }

    @Test
    fun `a retryable failure is retried with growing delays until accepted`() = runTest {
        val relay = FakeRelay(this, RelayOutcome.Retry(null), RelayOutcome.Retry(null), RelayOutcome.Accepted)

        assertEquals(listOf(RelayOutcome.Accepted), upload(relay).map { it.second })
        assertEquals(listOf(0L, 1_000L, 3_000L), relay.sentAt)
    }

    @Test
    fun `the delay the relay asks for wins over the backoff`() = runTest {
        val relay = FakeRelay(this, RelayOutcome.Retry(30.seconds), RelayOutcome.Accepted)

        upload(relay)

        assertEquals(listOf(0L, 30_000L), relay.sentAt)
    }

    @Test
    fun `a longer delay asked by the relay is capped at 5 minutes`() = runTest {
        val relay = FakeRelay(this, RelayOutcome.Retry(1_000.seconds), RelayOutcome.Accepted)

        upload(relay)

        assertEquals(listOf(0L, 300_000L), relay.sentAt)
    }

    @Test
    fun `a rejected event is not retried`() = runTest {
        val rejected = RelayOutcome.Rejected(400, "invalid_request")
        val relay = FakeRelay(this, rejected)

        assertEquals(listOf<RelayOutcome>(rejected), upload(relay).map { it.second })
        assertEquals(1, relay.sentAt.size)
    }

    @Test
    fun `delays stop growing at 5 minutes and the uploader gives up after 12 attempts`() = runTest {
        val relay = FakeRelay(this, RelayOutcome.Retry(null))

        assertEquals(listOf<RelayOutcome>(RelayOutcome.Retry(null)), upload(relay).map { it.second })
        assertEquals(
            listOf(1L, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300).map { it * 1_000 },
            relay.sentAt.zipWithNext { a, b -> b - a },
        )
    }
}
