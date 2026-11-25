package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Test

class NotificationEventContractTest {
    @Test
    fun `the protocol example decodes and encodes back to the same JSON`() {
        val example = ProtocolFiles.example("notification-event")

        val event = ProtocolJson.decodeFromString<NotificationEvent>(example)

        assertEquals(Json.parseToJsonElement(example), Json.parseToJsonElement(ProtocolJson.encodeToString(event)))
    }

    @Test
    fun `an event without optional text keeps every key and passes the schema`() {
        val event = NotificationEvent(
            eventId = "0b6f5f3e-2c1d-4f6a-9e8b-7a6c5d4e3f21",
            sourcePackage = "org.example.mail",
            sourceApp = null,
            notificationKey = "0|org.example.mail|7|null|10001",
            groupKey = null,
            postedAt = "2026-11-25T08:30:00.250Z",
            title = null,
            body = null,
            subtext = null,
            category = null,
            isOngoing = false,
            isClearable = true,
            isGroupSummary = false,
            replyable = false,
            actions = emptyList(),
        )

        val json = ProtocolJson.encodeToString(event)

        assertEquals(emptyList<Any>(), ProtocolFiles.schemaErrors("notification-event", json))
        assertEquals(15, Json.parseToJsonElement(json).jsonObject.size)
    }
}
