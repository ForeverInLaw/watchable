package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Body of `POST /v1/events/notification` (TZ §5.4, protocol/schema/notification-event.schema.json).
 * No property has a default, so every key, including explicit nulls, is always encoded.
 */
@Serializable
data class NotificationEvent(
    @SerialName("event_id") val eventId: String,
    @SerialName("source_package") val sourcePackage: String,
    @SerialName("source_app") val sourceApp: String?,
    @SerialName("notification_key") val notificationKey: String,
    @SerialName("group_key") val groupKey: String?,
    /** RFC3339 UTC with the `Z` suffix. */
    @SerialName("posted_at") val postedAt: String,
    val title: String?,
    val body: String?,
    val subtext: String?,
    val category: String?,
    @SerialName("is_ongoing") val isOngoing: Boolean,
    @SerialName("is_clearable") val isClearable: Boolean,
    @SerialName("is_group_summary") val isGroupSummary: Boolean,
    val replyable: Boolean,
    val actions: List<EventAction>,
)

/** An action the watch can perform on the notification; MVP only knows text replies. */
@Serializable
data class EventAction(
    val id: String,
    val title: String,
    val type: EventActionType,
)

@Serializable
enum class EventActionType {
    /** The action takes the reply text. */
    @SerialName("text")
    TEXT,
}
