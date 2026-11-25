package io.github.foreverinlaw.personalwatch.core.protocol

import kotlinx.serialization.json.Json

/** JSON settings for protocol bodies: unknown keys from a newer relay are tolerated on decode. */
val ProtocolJson: Json = Json { ignoreUnknownKeys = true }
