package io.github.foreverinlaw.personalwatch.companion

import io.github.foreverinlaw.personalwatch.core.network.RelayOutcome
import io.github.foreverinlaw.personalwatch.core.protocol.FcmMessage
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyExecute
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyFailure
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyResult
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ReplyCommandsTest {
    private val executed = mutableListOf<ReplyExecute>()
    private val reported = mutableListOf<Pair<String, ReplyResult>>()

    private val commands = ReplyCommands(
        execute = { reply ->
            executed += reply
            ReplyResult.Failed(ReplyFailure.NOTIFICATION_GONE)
        },
        report = { replyId, result ->
            reported += replyId to result
            RelayOutcome.Accepted(Unit)
        },
    )

    private fun message(id: String) = FcmMessage.Reply(
        id = id,
        payload = ReplyExecute(
            replyId = id,
            eventId = "018f3a5e-7c2b-7d4e-9a1b-3c5d7e9f1a2b",
            notificationKey = "0|com.whatsapp|1234|null|10001",
            sourcePackage = "com.whatsapp",
            text = "Ок",
        ),
    )

    @Test
    fun `a reply is executed and its result reported to the relay`() = runTest {
        val handled = commands.receive(message(REPLY_ID))

        assertEquals(
            ReplyCommands.Handled(ReplyResult.Failed(ReplyFailure.NOTIFICATION_GONE), RelayOutcome.Accepted(Unit)),
            handled,
        )
        assertEquals(listOf(message(REPLY_ID).payload), executed)
        assertEquals(listOf(REPLY_ID to ReplyResult.Failed(ReplyFailure.NOTIFICATION_GONE)), reported)
    }

    @Test
    fun `a message with an envelope id already seen is dropped without a result`() = runTest {
        commands.receive(message(REPLY_ID))

        val again = commands.receive(message(REPLY_ID))

        assertNull(again)
        assertEquals(1, executed.size)
        assertEquals(1, reported.size)
    }

    @Test
    fun `a message with another envelope id is executed`() = runTest {
        commands.receive(message(REPLY_ID))

        commands.receive(message("7d1e0c4b-3f5a-4b6c-8d7e-9f0a1b2c3d4e"))

        assertEquals(2, executed.size)
    }

    private companion object {
        const val REPLY_ID = "4c9e2f1a-8b3d-4e6f-a5c7-2d1b9e8f7a60"
    }
}
