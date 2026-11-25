package io.github.foreverinlaw.personalwatch.companion

import android.app.Application
import android.util.Log
import io.github.foreverinlaw.personalwatch.core.network.EventUploader
import io.github.foreverinlaw.personalwatch.core.network.RelayClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.time.Instant

/** Holds the app-wide objects the listener service and the screen share. */
class CompanionApp : Application() {
    val relayStatus = RelayStatus()

    /** Null when the build carries no usable relay URL or token. */
    val uploader: EventUploader? by lazy {
        val url = BuildConfig.RELAY_URL.toHttpUrlOrNull() ?: return@lazy null
        // OkHttp refuses header values outside printable ASCII, which would fail every upload.
        if (BuildConfig.RELAY_TOKEN.isBlank() || BuildConfig.RELAY_TOKEN.any { it !in ' '..'~' }) return@lazy null
        val client = RelayClient(url, BuildConfig.RELAY_TOKEN)
        EventUploader(
            scope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
            send = client::postNotification,
            onFinished = { event, outcome ->
                // Never log notification text (TZ §7.8).
                Log.i(TAG, "event ${event.eventId}: $outcome")
                relayStatus.record(outcome, Instant.now())
            },
        )
    }

    val isRelayConfigured: Boolean get() = uploader != null

    private companion object {
        const val TAG = "CompanionApp"
    }
}
