package io.github.foreverinlaw.personalwatch.companion

import android.content.Context
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.time.Duration.Companion.seconds

/**
 * FCM through a Firebase app started by hand from the build's `firebase.*` values, without the
 * google-services plugin or a google-services.json in the repository (TZ §7.5).
 */
class Fcm private constructor() {
    /** This Companion's FCM token; null when Firebase cannot hand one out now, for example offline. */
    suspend fun token(): String? = try {
        withTimeoutOrNull(TOKEN_TIMEOUT) { FirebaseMessaging.getInstance().token.await() }
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        // Firebase fails the token task with whatever went wrong; the next start or onNewToken retries.
        Log.w(TAG, "no FCM token", error)
        null
    }

    companion object {
        private const val TAG = "Fcm"
        private val TOKEN_TIMEOUT = 10.seconds

        /** Starts Firebase; null when the build lacks any `firebase.*` value, so FCM is not configured. */
        fun start(context: Context): Fcm? {
            val values = listOf(
                BuildConfig.FIREBASE_PROJECT_ID,
                BuildConfig.FIREBASE_APP_ID,
                BuildConfig.FIREBASE_API_KEY,
                BuildConfig.FIREBASE_SENDER_ID,
            )
            if (values.any { it.isBlank() }) return null
            val options = FirebaseOptions.Builder()
                .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                .setApplicationId(BuildConfig.FIREBASE_APP_ID)
                .setApiKey(BuildConfig.FIREBASE_API_KEY)
                .setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
                .build()
            // Once per process; Robolectric creates the Application again for every test in one JVM.
            if (FirebaseApp.getApps(context).isEmpty()) FirebaseApp.initializeApp(context, options)
            return Fcm()
        }
    }
}
