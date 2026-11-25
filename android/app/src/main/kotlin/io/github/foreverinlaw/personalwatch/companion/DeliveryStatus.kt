package io.github.foreverinlaw.personalwatch.companion

import io.github.foreverinlaw.personalwatch.core.network.RelayOutcome
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.time.Instant

/** The last event's fate at the relay, for the status screen. */
class DeliveryStatus {
    data class Delivery(val outcome: RelayOutcome, val at: Instant)

    private val last = MutableStateFlow<Delivery?>(null)
    val lastDelivery: StateFlow<Delivery?> = last.asStateFlow()

    fun record(outcome: RelayOutcome, at: Instant) {
        last.value = Delivery(outcome, at)
    }
}
