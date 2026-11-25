package io.github.foreverinlaw.personalwatch.core.notifications

import kotlin.math.abs
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds

/**
 * Remembers what each notification key last showed, by post time, to drop reposts that bring
 * nothing new: apps re-post a notification on every update, often with the same text.
 */
internal class RecentPosts<C>(private val window: Duration) {
    private class Seen<C>(val content: C, val postTime: Long)

    private val lastSeen = HashMap<String, Seen<C>>()

    /**
     * Records that [key] showed [content] at [postTime] (epoch milliseconds) and returns true when
     * it showed the same content less than the window before.
     */
    fun recordAndCheckRepeat(key: String, content: C, postTime: Long): Boolean {
        // Absolute distance: a post time earlier than the last one (clock change, late callback)
        // must not keep a stale entry alive.
        lastSeen.values.removeIf { abs(postTime - it.postTime).milliseconds >= window }
        val previous = lastSeen.put(key, Seen(content, postTime))
        return previous?.content == content
    }
}
