package io.github.foreverinlaw.personalwatch.core.network

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteRequest
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteResponse
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

/**
 * The relay as the Companion sees it once paired (TZ F1): pairing keeps the device token and ids
 * in [store], events go out with that token, and a token the relay no longer accepts is forgotten,
 * so the Companion shows itself unpaired until the user enters a new code.
 */
class PairedRelay(private val client: RelayClient, private val store: DataStore<Preferences>) {
    /** The credentials from the last pairing, or null while unpaired. */
    val credentials: Flow<PairCompleteResponse?> = store.data.map { preferences ->
        PairCompleteResponse(
            androidDeviceId = preferences[ANDROID_DEVICE_ID] ?: return@map null,
            androidDeviceToken = preferences[ANDROID_DEVICE_TOKEN] ?: return@map null,
            watchDeviceId = preferences[WATCH_DEVICE_ID] ?: return@map null,
        )
    }

    /**
     * Enters the [code] the watch shows; on success the new credentials replace the old ones.
     * Not cancellable: once the relay takes the code it revokes the old devices, so the answer
     * must be saved even if the caller, such as a screen the user left, stops waiting.
     */
    suspend fun pair(code: String, name: String?): RelayOutcome<PairCompleteResponse> = withContext(NonCancellable) {
        val outcome = client.completePairing(PairCompleteRequest(pairingCode = code, name = name))
        if (outcome is RelayOutcome.Accepted) {
            store.edit {
                it[ANDROID_DEVICE_ID] = outcome.body.androidDeviceId
                it[ANDROID_DEVICE_TOKEN] = outcome.body.androidDeviceToken
                it[WATCH_DEVICE_ID] = outcome.body.watchDeviceId
            }
        }
        outcome
    }

    /** Sends [event] with the stored token; unpaired, it is refused as the relay would refuse it. */
    suspend fun postNotification(event: NotificationEvent): RelayOutcome<Unit> {
        val token = credentials.first()?.androidDeviceToken ?: return INVALID_TOKEN
        val outcome = client.postNotification(token, event)
        // TZ §5.10: the relay revoked the token, which only a re-pair fixes.
        if (outcome == INVALID_TOKEN) forget(token)
        return outcome
    }

    /** Drops the credentials unless a pairing has replaced [token] meanwhile. */
    private suspend fun forget(token: String) {
        store.edit {
            if (it[ANDROID_DEVICE_TOKEN] == token) it.clear()
        }
    }

    private companion object {
        val ANDROID_DEVICE_ID = stringPreferencesKey("android_device_id")
        val ANDROID_DEVICE_TOKEN = stringPreferencesKey("android_device_token")
        val WATCH_DEVICE_ID = stringPreferencesKey("watch_device_id")
        val INVALID_TOKEN = RelayOutcome.Rejected(401, "invalid_token")
    }
}
