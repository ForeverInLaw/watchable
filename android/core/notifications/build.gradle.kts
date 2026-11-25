// Android-free filtering, dedup and normalization of posted notifications.
plugins {
    alias(libs.plugins.kotlin.jvm)
}

kotlin { jvmToolchain(21) }

dependencies {
    api(project(":core:protocol"))

    testImplementation(libs.junit)
}
