package io.github.foreverinlaw.personalwatch.companion

import io.github.foreverinlaw.personalwatch.core.network.RelayOutcome
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.time.Instant

/** How the relay took the last event, for the status screen. */
class RelayStatus {
    data class Result(val outcome: RelayOutcome, val at: Instant)

    private val last = MutableStateFlow<Result?>(null)
    val lastResult: StateFlow<Result?> = last.asStateFlow()

    fun record(outcome: RelayOutcome, at: Instant) {
        last.value = Result(outcome, at)
    }
}
