package me.magnum.melonds.ui.setup

/**
 * Read-only setup diagnostics. A persisted grant is not a successful ROM scan or
 * a compatibility test; the UI deliberately makes that distinction explicit.
 */
data class SetupStatus(
    val directoryCount: Int,
    val readableDirectoryCount: Int,
    val writableDirectoryCount: Int,
    val isDsMode: Boolean,
    val usesCustomBios: Boolean,
    val showsBootScreen: Boolean,
    val savesNextToRom: Boolean,
    val hasSeparateSaveDirectory: Boolean,
    val jitEnabled: Boolean,
) {
    init {
        require(directoryCount >= 0)
        require(readableDirectoryCount in 0..directoryCount)
        require(writableDirectoryCount in 0..readableDirectoryCount)
    }

    enum class FolderStatus { NOT_CONFIGURED, MISSING_READ_PERMISSION, READ_ONLY, GRANTS_RECORDED }

    val folderStatus: FolderStatus
        get() = when {
            directoryCount == 0 -> FolderStatus.NOT_CONFIGURED
            readableDirectoryCount < directoryCount -> FolderStatus.MISSING_READ_PERMISSION
            writableDirectoryCount < directoryCount -> FolderStatus.READ_ONLY
            else -> FolderStatus.GRANTS_RECORDED
        }

    val usesInternalDsDirectBoot: Boolean
        // Runtime ignores a stale show-boot-screen preference when custom BIOS is off.
        get() = isDsMode && !usesCustomBios

    // This matches SettingsRepository.getSaveFileDirectory(rom): an unset
    // separate folder still falls back to the ROM's directory when known.
    val usesSeparateSaveDirectory: Boolean
        get() = !savesNextToRom && hasSeparateSaveDirectory
}

object SetupGuidePolicy {
    const val CURRENT_VERSION = 1

    fun shouldShowAutomatically(completedVersion: Int, restoringActivity: Boolean): Boolean =
        !restoringActivity && completedVersion < CURRENT_VERSION
}
