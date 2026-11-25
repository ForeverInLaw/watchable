// Protocol DTOs shared by the Companion modules; mirrors ../../protocol/schema.
plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
}

kotlin { jvmToolchain(21) }

dependencies {
    api(libs.kotlinx.serialization.json)

    testImplementation(libs.junit)
    testImplementation(libs.json.schema.validator)
}

// The contract tests read the schemas and examples straight from the repo-root protocol/.
tasks.test {
    val protocolDir = rootProject.layout.projectDirectory.dir("../protocol")
    inputs.dir(protocolDir).withPathSensitivity(PathSensitivity.RELATIVE)
    systemProperty("protocol.dir", protocolDir.asFile.absolutePath)
}
