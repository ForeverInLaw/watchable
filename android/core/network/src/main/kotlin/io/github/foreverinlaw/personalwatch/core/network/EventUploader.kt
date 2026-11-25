package io.github.foreverinlaw.personalwatch.core.network

import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.random.Random
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds

/**
 * Sends events to the relay one at a time, in the order they were posted, so the watch shows them
 * in that order too. Each event is resent with exponential backoff and jitter while the relay
 * answers that a retry can help, and later events wait meanwhile. Every delay, including one the
 * relay asks for with Retry-After, is capped at 5 minutes (TZ §5.1).
 * Pending events live in memory only and are lost with the process.
 */
class EventUploader(
    scope: CoroutineScope,
    private val send: suspend (NotificationEvent) -> RelayOutcome,
    /** Picks the actual delay up to the given backoff; full jitter by default. */
    private val jitter: (Duration) -> Duration = { Random.nextLong(it.inWholeMilliseconds + 1).milliseconds },
    /** Called once per event with the last outcome: accepted, rejected, or the retry it gave up on. */
    private val onFinished: (NotificationEvent, RelayOutcome) -> Unit,
) {
    private val queue = Channel<NotificationEvent>(Channel.UNLIMITED)

    init {
        scope.launch {
            for (event in queue) deliver(event)
        }
    }

    fun upload(event: NotificationEvent) {
        queue.trySend(event)
    }

    private suspend fun deliver(event: NotificationEvent) {
        var backoff = FIRST_BACKOFF
        var attempts = 1
        var outcome = send(event)
        while (outcome is RelayOutcome.Retry && attempts < MAX_ATTEMPTS) {
            delay((outcome.after ?: jitter(backoff)).coerceAtMost(MAX_BACKOFF))
            backoff = (backoff * 2).coerceAtMost(MAX_BACKOFF)
            outcome = send(event)
            attempts++
        }
        onFinished(event, outcome)
    }

    private companion object {
        val FIRST_BACKOFF = 1.seconds
        val MAX_BACKOFF = 5.minutes
        const val MAX_ATTEMPTS = 12
    }
}
