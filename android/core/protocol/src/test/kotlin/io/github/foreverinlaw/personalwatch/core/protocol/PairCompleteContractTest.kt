package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Test

class PairCompleteContractTest {
    @Test
    fun `the request encodes to the protocol example`() {
        val json = ProtocolJson.encodeToString(PairCompleteRequest(pairingCode = "48151623", name = "Pixel 8"))

        assertEquals(Json.parseToJsonElement(ProtocolFiles.example("pair-complete-request")), Json.parseToJsonElement(json))
    }

    @Test
    fun `a request with the FCM token encodes to the protocol example`() {
        val request = PairCompleteRequest(
            pairingCode = "48151623",
            name = "Pixel 8",
            fcmToken = "dQw4w9WgXcQ:APA91bHun4MxP5egoKMwt2KZFBaFUH-1RYqx",
        )

        assertEquals(
            Json.parseToJsonElement(ProtocolFiles.example("pair-complete-request.fcm")),
            Json.parseToJsonElement(ProtocolJson.encodeToString(request)),
        )
    }

    @Test
    fun `the push token request encodes to the protocol example`() {
        val json = ProtocolJson.encodeToString(PushTokenRequest("573fbc335fd665296c6f0ab8c276ec5cc831270e332dfd8a2d31091eae0583b4"))

        assertEquals(Json.parseToJsonElement(ProtocolFiles.example("push-token-request")), Json.parseToJsonElement(json))
    }

    @Test
    fun `a request without a name leaves the key out and passes the schema`() {
        val json = ProtocolJson.encodeToString(PairCompleteRequest(pairingCode = "00000042", name = null))

        assertEquals("""{"pairing_code":"00000042","platform":"android"}""", json)
        assertEquals(emptyList<Any>(), ProtocolFiles.schemaErrors("pair-complete-request", json))
    }

    @Test
    fun `the protocol example of the response decodes`() {
        val response = ProtocolJson.decodeFromString<PairCompleteResponse>(ProtocolFiles.example("pair-complete-response"))

        assertEquals(
            PairCompleteResponse(
                androidDeviceId = "c99d4f00-ecdc-4d75-879e-473f63bcc9c8",
                androidDeviceToken = "sDxL4rPeYN53lN-rmJIMmRJXVz5Ytnp2uB5P_WCo6CI",
                watchDeviceId = "12861bc2-25be-4ee8-89f4-a568cccacc64",
            ),
            response,
        )
    }
}
