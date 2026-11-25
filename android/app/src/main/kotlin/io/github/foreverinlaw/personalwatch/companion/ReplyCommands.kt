package io.github.foreverinlaw.personalwatch.companion

import io.github.foreverinlaw.personalwatch.core.network.RelayOutcome
import io.github.foreverinlaw.personalwatch.core.protocol.FcmMessage
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyExecute
import io.github.foreverinlaw.personalwatch.core.protocol.ReplyResult

/**
 * Runs each `reply.execute` from the relay once and reports its result (TZ §7.4). FCM may deliver a
 * message twice, so one whose envelope id was already seen is dropped without running it or
 * reporting anything: a reply sent twice would show up twice in the chat. [execute] sends the reply
 * through the notification, [report] tells the relay the result. The seen ids live in memory, the
 * last [REMEMBERED] of them, and go with the process.
 */
class ReplyCommands(
    private val execute: (ReplyExecute) -> ReplyResult,
    private val report: suspend (replyId: String, result: ReplyResult) -> RelayOutcome<Unit>,
) {
    private val seen = LinkedHashSet<String>()

    /** What became of [message] and what the relay made of the result; null for a message already run. */
    suspend fun receive(message: FcmMessage.Reply): Handled? {
        if (!firstSeen(message.id)) return null
        val result = execute(message.payload)
        return Handled(result, report(message.payload.replyId, result))
    }

    @Synchronized
    private fun firstSeen(id: String): Boolean {
        if (!seen.add(id)) return false
        if (seen.size > REMEMBERED) seen.remove(seen.first())
        return true
    }

    data class Handled(val result: ReplyResult, val reported: RelayOutcome<Unit>)

    private companion object {
        const val REMEMBERED = 100
    }
}
