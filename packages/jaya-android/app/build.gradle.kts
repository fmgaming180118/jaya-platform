import java.net.URI
import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.google.devtools.ksp)
    alias(libs.plugins.jetbrains.kotlin.plugin.serialization)
}

val localProps = Properties().also { props ->
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { props.load(it) }
}

fun validateApiUrl(value: String, allowLocalCleartext: Boolean): String {
    val uri = try {
        URI(value)
    } catch (error: Exception) {
        throw GradleException("Invalid JAYA API URL", error)
    }
    val host = uri.host ?: throw GradleException("JAYA API URL must include a host")
    val secure = uri.scheme.equals("https", ignoreCase = true)
    val localDebug = allowLocalCleartext &&
        uri.scheme.equals("http", ignoreCase = true) &&
        host.lowercase() in setOf("10.0.2.2", "127.0.0.1", "localhost")

    if (!secure && !localDebug) {
        throw GradleException(
            "JAYA API URL must use HTTPS; cleartext is limited to loopback debug builds"
        )
    }
    if (uri.userInfo != null || uri.fragment != null) {
        throw GradleException("JAYA API URL cannot contain credentials or fragments")
    }
    return if (value.endsWith('/')) value else "$value/"
}

fun String.asBuildConfigString(): String =
    "\"${replace("\\", "\\\\").replace("\"", "\\\"")}\""

val debugJayaApiUrl = validateApiUrl(
    localProps.getProperty("JAYA_DEBUG_API_URL") ?: "http://10.0.2.2:8000/",
    allowLocalCleartext = true,
)
val releaseJayaApiUrl = validateApiUrl(
    localProps.getProperty("JAYA_API_URL") ?: "https://127.0.0.1:8443/",
    allowLocalCleartext = false,
)
val modelSha256 = localProps.getProperty("JAYA_MODEL_SHA256")?.trim().orEmpty().also { digest ->
    if (digest.isNotEmpty() && !digest.matches(Regex("[a-fA-F0-9]{64}"))) {
        throw GradleException("JAYA_MODEL_SHA256 must be a 64-character SHA-256 digest")
    }
}

android {
    namespace = "com.example.jaya"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.example.jaya"
        minSdk = 24
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "JAYA_MODEL_SHA256", modelSha256.asBuildConfigString())
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            buildConfigField("String", "JAYA_API_URL", releaseJayaApiUrl.asBuildConfigString())
            optimization {
                enable = false
            }
        }
        debug {
            buildConfigField("String", "JAYA_API_URL", debugJayaApiUrl.asBuildConfigString())
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.accompanist.permissions)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)
    implementation(libs.androidx.compose.adaptive)
    implementation(libs.androidx.compose.adaptive.layout)
    implementation(libs.androidx.compose.adaptive.navigation3)
    implementation(libs.adaptive.navigation.suite)
    implementation(libs.compose.markdown)
    implementation(libs.androidx.compose.material.icons.core)
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.biometric)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.viewmodel.navigation3)
    implementation(libs.androidx.navigation3.runtime)
    implementation(libs.androidx.navigation3.ui)
    implementation(libs.androidx.room.ktx)
    implementation(libs.androidx.room.runtime)
    implementation(libs.coil.compose)
    implementation(libs.converter.moshi)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.serialization.core)
    implementation(libs.logging.interceptor)
    implementation(libs.material)
    implementation(libs.moshi.kotlin)
    implementation(libs.okhttp)
    implementation(libs.play.services.location)
    implementation(libs.retrofit)
    testImplementation(libs.androidx.core)
    testImplementation(libs.androidx.junit)
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.runner)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
    "ksp"(libs.androidx.room.compiler)
    "ksp"(libs.moshi.kotlin.codegen)
}
