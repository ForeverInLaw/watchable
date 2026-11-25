package io.github.foreverinlaw.personalwatch.companion

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * The shade as the connected notification listener sees it, for replies that arrive over FCM
 * (TZ §7.4). Empty while the listener is not connected.
 */
class ConnectedShade {
    @Volatile
    private var listener: NotificationListenerService? = null

    fun connected(listener: NotificationListenerService) {
        this.listener = listener
    }

    fun disconnected(listener: NotificationListenerService) {
        if (this.listener === listener) this.listener = null
    }

    /** The notification with [key] if it is still in the shade. */
    fun find(key: String): StatusBarNotification? = listener?.getActiveNotifications(arrayOf(key))?.firstOrNull()
}
