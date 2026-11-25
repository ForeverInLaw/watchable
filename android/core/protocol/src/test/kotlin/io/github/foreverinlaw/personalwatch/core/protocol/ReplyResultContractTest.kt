package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Test

class ReplyResultContractTest {
    private fun encoded(result: ReplyResult) = Json.parseToJsonElement(ProtocolJson.encodeToString(result))

    @Test
    fun `a sent reply encodes to the protocol example`() {
        assertEquals(Json.parseToJsonElement(ProtocolFiles.example("reply-result")), encoded(ReplyResult.Sent))
    }

    @Test
    fun `a reply to a notification that is gone encodes to the protocol example`() {
        assertEquals(
            Json.parseToJsonElement(ProtocolFiles.example("reply-result.failed")),
            encoded(ReplyResult.Failed(ReplyFailure.NOTIFICATION_GONE)),
        )
    }

    @Test
    fun `a reply without a free text action passes the schema`() {
        val json = ProtocolJson.encodeToString<ReplyResult>(ReplyResult.Failed(ReplyFailure.REMOTE_INPUT_UNSUPPORTED))

        assertEquals("""{"status":"failed","error":"remote_input_unsupported"}""", json)
        assertEquals(emptyList<Any>(), ProtocolFiles.schemaErrors("reply-result", json))
    }
}
