plugins {
    id("com.android.application")
}

android {
    namespace = "com.brandora.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.brandora.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.webkit:webkit:1.14.0")
}

// The UI is the same React build the server uses (frontend/dist), bundled into the APK.
val webDist = rootDir.resolve("../frontend/dist")
val syncWeb by tasks.registering(Sync::class) {
    doFirst {
        require(webDist.resolve("index.html").exists()) {
            "frontend/dist is missing. Run `npm run build` in frontend/ first."
        }
    }
    from(webDist)
    into(layout.projectDirectory.dir("src/main/assets/www"))
}
tasks.named("preBuild") { dependsOn(syncWeb) }
