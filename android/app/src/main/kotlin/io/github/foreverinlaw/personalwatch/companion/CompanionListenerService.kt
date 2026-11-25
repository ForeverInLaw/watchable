package io.github.foreverinlaw.personalwatch.companion

import android.content.ComponentName
import android.content.pm.PackageManager
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import io.github.foreverinlaw.personalwatch.core.notifications.NotificationPipeline
import io.github.foreverinlaw.personalwatch.core.notifications.PipelineResult

/** Receives every posted notification once the user grants notification access (TZ §7.3). */
class CompanionListenerService : NotificationListenerService() {
    private val pipeline by lazy { NotificationPipeline(ownPackage = packageName) }

    /** The system can unbind the listener, for example after the app is updated (TZ §7.3). */
    override fun onListenerDisconnected() {
        requestRebind(ComponentName(this, CompanionListenerService::class.java))
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val uploader = (application as CompanionApp).uploader ?: return
        val posted = sbn.toPostedNotification(appLabel = appLabel(sbn.packageName))
        when (val result = pipeline.process(posted) { activeNotifications.orEmpty().map { it.toActiveNotification() } }) {
            // Unpaired, PairedRelay refuses the event without a request (TZ F1).
            is PipelineResult.Forward -> uploader.upload(result.event)
            is PipelineResult.Skip -> Log.d(TAG, "skipped ${sbn.key}: ${result.reason}")
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        pipeline.forget(sbn.key)
    }

    override fun onListenerConnected() {
        pipeline.syncWithShade(activeNotifications.orEmpty().map { it.toPostedNotification(appLabel(it.packageName)) })
    }

    /** Needs the launcher-app <queries> entry in the manifest to see other packages. */
    private fun appLabel(packageName: String): String? = try {
        packageManager.getApplicationLabel(packageManager.getApplicationInfo(packageName, 0)).toString()
    } catch (_: PackageManager.NameNotFoundException) {
        null
    }

    private companion object {
        const val TAG = "CompanionListener"
    }
}
