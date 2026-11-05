package me.magnum.melonds.ui.setup

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SetupStatusTest {
    private fun status(
        count: Int = 1,
        read: Int = count,
        write: Int = read,
        ds: Boolean = true,
        custom: Boolean = false,
        bootScreen: Boolean = false,
        nextToRom: Boolean = true,
        separate: Boolean = false,
    ) = SetupStatus(count, read, write, ds, custom, bootScreen, nextToRom, separate, true)

    @Test fun noDirectoriesIsNotReadyEvenWithZeroMissingGrants() {
        assertEquals(SetupStatus.FolderStatus.NOT_CONFIGURED, status(count = 0).folderStatus)
    }

    @Test fun allConfiguredDirectoriesNeedReadGrants() {
        assertEquals(SetupStatus.FolderStatus.MISSING_READ_PERMISSION, status(count = 2, read = 1).folderStatus)
    }

    @Test fun readOnlyGrantsAreNotAdvertisedAsWritable() {
        assertEquals(SetupStatus.FolderStatus.READ_ONLY, status(count = 2, write = 1).folderStatus)
    }

    @Test fun completeGrantsOnlyMeanGrantsAreRecorded() {
        assertEquals(SetupStatus.FolderStatus.GRANTS_RECORDED, status(count = 2).folderStatus)
    }

    @Test fun missingReadGrantTakesPrecedenceOverMissingWriteGrant() {
        assertEquals(SetupStatus.FolderStatus.MISSING_READ_PERMISSION, status(count = 2, read = 0, write = 0).folderStatus)
    }

    @Test fun internalDirectBootUsesEffectiveBiosConfiguration() {
        assertTrue(status().usesInternalDsDirectBoot)
        assertFalse(status(ds = false).usesInternalDsDirectBoot)
        assertFalse(status(custom = true).usesInternalDsDirectBoot)
        assertTrue(status(bootScreen = true).usesInternalDsDirectBoot)
        assertFalse(status(custom = true, bootScreen = true).usesInternalDsDirectBoot)
    }

    @Test fun separateSaveFolderRequiresSelectionAndDisabledRomPreference() {
        assertTrue(status(nextToRom = false, separate = true).usesSeparateSaveDirectory)
        assertFalse(status(nextToRom = true, separate = true).usesSeparateSaveDirectory)
        assertFalse(status(nextToRom = false, separate = false).usesSeparateSaveDirectory)
        assertFalse(status(nextToRom = true, separate = false).usesSeparateSaveDirectory)
    }

    @Test(expected = IllegalArgumentException::class)
    fun invalidReadCountCannotProduceMisleadingStatus() {
        status(count = 1, read = 2)
    }

    @Test(expected = IllegalArgumentException::class)
    fun invalidWriteCountCannotProduceMisleadingStatus() {
        status(count = 1, read = 0, write = 1)
    }

    @Test(expected = IllegalArgumentException::class)
    fun negativeDirectoryCountIsRejected() {
        status(count = -1)
    }

    @Test fun firstLaunchShowsGuide() {
        assertTrue(SetupGuidePolicy.shouldShowAutomatically(completedVersion = 0, restoringActivity = false))
    }

    @Test fun reviewedGuideDoesNotReopenAutomatically() {
        assertFalse(SetupGuidePolicy.shouldShowAutomatically(SetupGuidePolicy.CURRENT_VERSION, false))
    }

    @Test fun restoredActivityDoesNotLaunchAnotherGuideOnTop() {
        assertFalse(SetupGuidePolicy.shouldShowAutomatically(completedVersion = 0, restoringActivity = true))
    }

    @Test fun newerCompletedGuideSurvivesAppDowngrade() {
        assertFalse(SetupGuidePolicy.shouldShowAutomatically(SetupGuidePolicy.CURRENT_VERSION + 1, false))
    }
}
