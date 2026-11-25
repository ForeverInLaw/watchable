package io.github.foreverinlaw.personalwatch.core.protocol

import com.networknt.schema.InputFormat
import com.networknt.schema.Schema
import com.networknt.schema.SchemaLocation
import com.networknt.schema.SchemaRegistry
import com.networknt.schema.SpecificationVersion
import java.io.File

/** The repo-root protocol/ directory the contract tests read schemas and examples from. */
object ProtocolFiles {
    private val dir = File(System.getProperty("protocol.dir"))

    private val registry =
        // fetchRemoteResources lets the loader read schemas, and the ones they $ref, from their file: IRIs.
        SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12) { registry ->
            registry.schemaLoader { it.fetchRemoteResources() }
        }

    /** Reads `examples/<name>.json`. */
    fun example(name: String): String = dir.resolve("examples/$name.json").readText()

    /** Validates [json] against `schema/<name>.schema.json` with format assertions on; empty when it passes. */
    fun schemaErrors(name: String, json: String): List<Any> = schema(name)
        .validate(json, InputFormat.JSON) { context -> context.executionConfig { it.formatAssertionsEnabled(true) } }

    private fun schema(name: String): Schema = registry
        .getSchema(SchemaLocation.of(dir.resolve("schema/$name.schema.json").toPath().toUri().toString()))
        .apply { initializeValidators() }
}
