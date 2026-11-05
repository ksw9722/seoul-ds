# Historical upstream README (melonDS Android 2.0.1)

This text preserves upstream usage/build context. It is **not** the current Seoul DS setup guide. Upstream screenshot and store-badge sections were removed from this fork to avoid bundling game imagery or implying an upstream store identity. Original source: https://github.com/rafaelvcaetano/melonDS-android/tree/2.0.1 .

# melonDS Android port
Android port of [melonDS](https://melonds.kuribo64.net/), a DS and DSi emulator.

# Missing Features
*  Local Multiplayer
*  DSi SD card support
*  Customizable button skins
*  More display filters

# Performance
Performance is solid on 64 bit devices with thread rendering and JIT enabled, and should run at full speed on flagship devices. Performance on older devices, specially
32 bit devices, is very poor due to the lack of JIT support.

# Integration with third-party frontends
It's possible to launch melonDS from third part frontends. For that, you will need to have the ROMs you want to launch already scanned by melonDS. Then, you can configure your
third-party frontend with the following configuration:
*  Package name: `me.magnum.melonds`
*  Activity name: `me.magnum.melonds.ui.emulator.EmulatorActivity`
*  Parameters (choose one):
    * Intent data (preferred) - a URI of the NDS ROM (ZIP and 7z files are supported). Ensure [read permission is granted](https://developer.android.com/reference/android/content/Intent#FLAG_GRANT_READ_URI_PERMISSION)
    * `uri` (deprecated) - a string with the [SAF](https://developer.android.com/guide/topics/providers/create-document-provider) URI of the NDS ROM (ZIP and 7z files are supported)
    * `PATH` (deprecated) - a string with the absolute path to the NDS ROM (ZIP and 7z files are supported)

### Pegasus metadata files
* [melonds.metadata.txt](https://github.com/rafaelvcaetano/melonDS-android/blob/2.0.1/.github/pegasus/melonds.metadata.txt) 
* [melonds-nightly.metadata.txt](https://github.com/rafaelvcaetano/melonDS-android/blob/2.0.1/.github/pegasus/melonds-nightly.metadata.txt) 

### Info regarding save files
When launching ROMs from third-party frontends, if melonDS hasn't scanned that particular ROM previously, it won't be able to create the save file next to the ROM file if the
option "Save next to ROM file" is enabled in the settings or the save file directory is not set. Instead, melonDS will create a save file in
`Android/data/me.magnum.melonds/files/saves`

# Nightly Builds

To have access to the latest changes, you can install nightly builds that you can find [here](https://github.com/rafaelvcaetano/melonDS-android/releases/tag/nightly-release).

Be aware that these builds can contain more bugs than usual and you may need to clear your app data to get it to work properly after updates.

# Building
To build the project you will need Android SDK, NDK and CMake.

## Build steps:
1.  Clone the project, including submodules with:
    
    `git clone --recurse-submodules https://github.com/rafaelvcaetano/melonDS-android.git`
2.  Install the Android SDK, NDK and CMake
3.  Build with:
    1.  Unix: `./gradlew :app:assembleGitHubProdDebug`
    2.  Windows: `gradlew.bat :app:assembleGitHubProdDebug`
4.  The generated APK can be found at `app/gitHubProd/debug`

If you want to create a release build, you will need to modify your `local.properties` file to include the following fields:  
*  `MELONDS_KEYSTORE=<path_to_your_keystore>`
*  `MELONDS_KEYSTORE_PASSWORD=<keystore_password>`
*  `MELONDS_KEY_ALIAS=<name_of_your_key_alias>`
*  `MELONDS_KEY_PASSWORD=<key_alias_password>`
