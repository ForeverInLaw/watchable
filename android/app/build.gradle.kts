import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// The relay URL is baked into the build from the gitignored local.properties (relay.url); without it
// the app builds and reports the relay as not configured. The device token comes from pairing (TZ F1).
val localProperties = Properties().apply {
    rootProject.file("local.properties").takeIf { it.isFile }?.reader()?.use(::load)
}

fun buildConfigString(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

android {
    namespace = "io.github.foreverinlaw.personalwatch.companion"
    compileSdk {
        version = release(37) { minorApiLevel = 1 }
    }

    defaultConfig {
        applicationId = "io.github.foreverinlaw.personalwatch.companion"
        minSdk { version = release(31) }
        targetSdk { version = release(35) }
        versionCode = 1
        versionName = "0.1.0"

        buildConfigField("String", "RELAY_URL", buildConfigString(localProperties.getProperty("relay.url", "")))
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }

    testOptions {
        // Robolectric reads the merged manifest, and with it targetSdk, only with resources included.
        unitTests.isIncludeAndroidResources = true
    }
}

dependencies {
    implementation(project(":core:notifications"))
    implementation(project(":core:network"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
}
