package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FcmMessageContractTest {
    /** FCM `data` as the Companion receives it: the protocol example, every value a string. */
    private val data: Map<String, String> = Json.parseToJsonElement(ProtocolFiles.example("fcm-envelope.reply-execute"))
        .jsonObject.mapValues { it.value.jsonPrimitive.content }

    @Test
    fun `the protocol example decodes into a reply`() {
        assertEquals(
            FcmMessage.Reply(
                id = "4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60",
                payload = ReplyExecute(
                    replyId = "4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60",
                    eventId = "018f3a5e-7c2b-7d4e-9a1b-3c5d7e9f1a2b",
                    notificationKey = "0|com.whatsapp|1234|null|10001",
                    sourcePackage = "com.whatsapp",
                    text = "Ок",
                ),
            ),
            FcmMessage.decode(data),
        )
    }

    @Test
    fun `a message of an unknown type is ignored`() {
        assertNull(FcmMessage.decode(data + ("type" to "music.play")))
    }

    @Test
    fun `a message of another protocol version is ignored`() {
        assertNull(FcmMessage.decode(data + ("v" to "2")))
    }

    @Test
    fun `a message without an envelope field is ignored`() {
        assertNull(FcmMessage.decode(data - "device_id"))
    }

    @Test
    fun `a reply whose payload is not the reply execute object is ignored`() {
        assertNull(FcmMessage.decode(data + ("payload" to """{"reply_id":"4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60"}""")))
        assertNull(FcmMessage.decode(data + ("payload" to "not json")))
    }
}
