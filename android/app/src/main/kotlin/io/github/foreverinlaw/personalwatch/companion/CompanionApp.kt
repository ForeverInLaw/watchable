package io.github.foreverinlaw.personalwatch.companion

import android.app.Application
import android.util.Log
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import io.github.foreverinlaw.personalwatch.core.network.EventUploader
import io.github.foreverinlaw.personalwatch.core.network.PairedRelay
import io.github.foreverinlaw.personalwatch.core.network.RelayClient
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteResponse
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.time.Instant

/** Holds the app-wide objects the listener service and the screens share. */
class CompanionApp : Application() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val relayStatus = RelayStatus()

    /** Null when the build carries no usable relay URL. */
    val relay: PairedRelay? by lazy {
        val url = BuildConfig.RELAY_URL.toHttpUrlOrNull() ?: return@lazy null
        // Under files/, which data_extraction_rules.xml keeps out of backup and device transfer.
        val store = PreferenceDataStoreFactory.create(scope = scope) { filesDir.resolve("datastore/pairing.preferences_pb") }
        PairedRelay(RelayClient(url), store)
    }

    /**
     * The current pairing, holding null while unpaired or not yet read from disk; null itself when
     * the relay is not configured. Read without suspending, so the listener can tell whether to send.
     */
    val pairing: StateFlow<PairCompleteResponse?>? by lazy {
        relay?.credentials?.stateIn(scope, SharingStarted.Eagerly, initialValue = null)
    }

    val uploader: EventUploader? by lazy {
        val relay = relay ?: return@lazy null
        EventUploader(
            scope = scope,
            send = relay::postNotification,
            onFinished = { event, outcome ->
                // Never log notification text (TZ §7.8).
                Log.i(TAG, "event ${event.eventId}: $outcome")
                relayStatus.record(outcome, Instant.now())
            },
        )
    }

    private companion object {
        const val TAG = "CompanionApp"
    }
}
