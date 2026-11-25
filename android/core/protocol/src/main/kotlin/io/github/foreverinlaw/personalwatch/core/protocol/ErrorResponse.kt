package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.Serializable

/** Body of every HTTP error response (TZ §5.1, protocol/schema/error.schema.json). */
@Serializable
data class ErrorResponse(val error: Error) {
    @Serializable
    data class Error(
        val code: String,
        val message: String,
        /** Whether resending the same request can succeed. */
        val retryable: Boolean,
    )
}
