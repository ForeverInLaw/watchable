package io.github.foreverinlaw.personalwatch.core.notifications

/**
 * Remembers what each notification key last showed, by post time, to drop reposts that bring
 * nothing new: apps re-post a notification on every update, often with the same text.
 */
internal class RecentPosts(private val windowMillis: Long) {
    private class Seen(val content: Any, val postTime: Long)

    private val lastSeen = HashMap<String, Seen>()

    /** True when [key] showed the same [content] less than the window before [postTime]. */
    fun isRepeat(key: String, content: Any, postTime: Long): Boolean {
        lastSeen.values.removeIf { postTime - it.postTime >= windowMillis }
        val previous = lastSeen.put(key, Seen(content, postTime))
        return previous?.content == content
    }
}
