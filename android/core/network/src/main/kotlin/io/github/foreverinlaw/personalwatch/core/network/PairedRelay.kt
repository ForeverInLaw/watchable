package io.github.foreverinlaw.personalwatch.core.network

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import io.github.foreverinlaw.personalwatch.core.protocol.NotificationEvent
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteRequest
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteResponse
import io.github.foreverinlaw.personalwatch.core.protocol.PushTokenRequest
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyResult
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * The relay as the Companion sees it once paired (TZ F1): pairing keeps the device token and ids
 * in [store], events go out with that token, and a token the relay no longer accepts is forgotten,
 * so the Companion shows itself unpaired until the user enters a new code.
 * The relay also keeps the Companion's FCM token, which [fcmToken] reads from Firebase (TZ §7.5).
 */
class PairedRelay(
    private val client: RelayClient,
    private val store: DataStore<Preferences>,
    private val fcmToken: suspend () -> String?,
) {
    private val pairing = Mutex()

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
     * One pairing or token update at a time, so a slow earlier answer cannot overwrite a later one.
     */
    suspend fun pair(code: String, name: String?): RelayOutcome<PairCompleteResponse> = pairing.withLock {
        withContext(NonCancellable) { completeAndSave(code, name) }
    }

    private suspend fun completeAndSave(code: String, name: String?): RelayOutcome<PairCompleteResponse> {
        val pushToken = fcmToken()
        val outcome = client.completePairing(PairCompleteRequest(pairingCode = code, name = name, fcmToken = pushToken))
        if (outcome is RelayOutcome.Accepted) {
            store.edit {
                it[ANDROID_DEVICE_ID] = outcome.body.androidDeviceId
                it[ANDROID_DEVICE_TOKEN] = outcome.body.androidDeviceToken
                it[WATCH_DEVICE_ID] = outcome.body.watchDeviceId
                if (pushToken != null) it[FCM_TOKEN] = pushToken else it.remove(FCM_TOKEN)
            }
        }
        return outcome
    }

    /**
     * Sends the relay the Companion's new FCM [token] unless the relay already has it. The token
     * counts as sent only once the relay took it, so a failed update is sent again next time.
     * Unpaired, it is refused without a request: pairing sends the token then.
     */
    suspend fun updatePushToken(token: String): RelayOutcome<Unit> = pairing.withLock {
        authorized { paired ->
            if (store.data.first()[FCM_TOKEN] == token) return@authorized RelayOutcome.Accepted(Unit)
            val deviceToken = paired.androidDeviceToken
            client.updatePushToken(deviceToken, paired.androidDeviceId, PushTokenRequest(token)).also { outcome ->
                if (outcome is RelayOutcome.Accepted) {
                    store.edit { if (it[ANDROID_DEVICE_TOKEN] == deviceToken) it[FCM_TOKEN] = token }
                }
            }
        }
    }

    /** Sends [event] with the stored token. */
    suspend fun postNotification(event: NotificationEvent): RelayOutcome<Unit> =
        authorized { client.postNotification(it.androidDeviceToken, event) }

    /** Reports what became of reply [replyId] with the stored token (TZ §5.6). */
    suspend fun postReplyResult(replyId: String, result: ReplyResult): RelayOutcome<Unit> =
        authorized { client.postReplyResult(it.androidDeviceToken, replyId, result) }

    /**
     * Runs [call] with the stored credentials; unpaired, it is refused as the relay would refuse it,
     * and a device token the relay refuses is forgotten.
     */
    private suspend fun <T> authorized(call: suspend (PairCompleteResponse) -> RelayOutcome<T>): RelayOutcome<T> {
        val paired = credentials.first() ?: return INVALID_TOKEN
        val outcome = call(paired)
        // TZ §5.10: the relay revoked the token, which only a re-pair fixes.
        if (outcome == INVALID_TOKEN) forget(paired.androidDeviceToken)
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
        // The FCM token the relay has for this Companion.
        val FCM_TOKEN = stringPreferencesKey("fcm_token")
        val INVALID_TOKEN = RelayOutcome.Rejected(401, "invalid_token")
    }
}
