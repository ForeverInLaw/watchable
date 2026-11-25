// Relay HTTP client, the Companion's pairing with it and the retrying uploader (TZ F1, §5.1, §5.10).
plugins {
    alias(libs.plugins.kotlin.jvm)
}

kotlin { jvmToolchain(21) }

dependencies {
    api(project(":core:protocol"))
    api(libs.kotlinx.coroutines.core)
    api(libs.okhttp)
    api(libs.datastore.preferences.core)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)
}
