object AppConfig {
    const val compileSdkVersion = 36
    const val targetSdkVersion = compileSdkVersion
    const val minSdkVersion = 24
    const val ndkVersion = "28.0.13004108"

    // The inherited settings migrator keys off this value; do not restart below 40.
    const val versionCode = 40
    const val versionName = "0.1.0-alpha01"
}
