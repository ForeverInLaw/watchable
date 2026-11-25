package io.github.foreverinlaw.personalwatch.companion

import android.app.Application
import android.util.Log
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import io.github.foreverinlaw.personalwatch.core.network.EventUploader
import io.github.foreverinlaw.personalwatch.core.network.PairedRelay
import io.github.foreverinlaw.personalwatch.core.network.RelayClient
import io.github.foreverinlaw.personalwatch.core.network.RelayOutcome
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
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
        // Firebase arrives with the reply path; until then pairing sends no FCM token.
        PairedRelay(RelayClient(url), store, fcmToken = { null })
    }

    val uploader: EventUploader? by lazy {
        val relay = relay ?: return@lazy null
        EventUploader(
            scope = scope,
            send = relay::postNotification,
            onFinished = { event, outcome ->
                // Never log notification text (TZ §7.8).
                Log.i(TAG, "event ${event.eventId}: $outcome")
                // An invalid token means unpaired, and the screen hides the last outcome while
                // unpaired; recorded, it would show up as the last outcome right after pairing.
                val unpaired = outcome is RelayOutcome.Rejected && outcome.code == "invalid_token"
                if (!unpaired) relayStatus.record(outcome, Instant.now())
            },
        )
    }

    private companion object {
        const val TAG = "CompanionApp"
    }
}
