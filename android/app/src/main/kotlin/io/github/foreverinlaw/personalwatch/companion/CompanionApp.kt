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
import kotlinx.coroutines.launch
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.time.Instant

/** Holds the app-wide objects the services and the screens share. */
class CompanionApp : Application() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val relayStatus = RelayStatus()

    /** Null when the build carries no Firebase options; set once in [onCreate]. */
    var fcm: Fcm? = null
        private set

    val connectedShade = ConnectedShade()

    /** Null when the build carries no usable relay URL, so there is no relay to take a result. */
    val replies: ReplyCommands? by lazy {
        val relay = relay ?: return@lazy null
        ReplyCommands(ReplyCommandHandler(this, connectedShade::find)::execute, relay::postReplyResult)
    }

    override fun onCreate() {
        super.onCreate()
        fcm = Fcm.start(this) ?: return
        // The token may have changed while the app was not running (TZ §7.5).
        syncFcmToken()
    }

    /** Sends the relay the current FCM token if it changed; unpaired, pairing sends it instead. */
    fun syncFcmToken() {
        val relay = relay ?: return
        scope.launch { Log.i(TAG, "FCM token update: ${relay.syncPushToken()}") }
    }

    /** Null when the build carries no usable relay URL. */
    val relay: PairedRelay? by lazy {
        val url = BuildConfig.RELAY_URL.toHttpUrlOrNull() ?: return@lazy null
        // Under files/, which data_extraction_rules.xml keeps out of backup and device transfer.
        val store = PreferenceDataStoreFactory.create(scope = scope) { filesDir.resolve("datastore/pairing.preferences_pb") }
        PairedRelay(RelayClient(url), store, fcmToken = { fcm?.token() })
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
