package me.magnum.melonds.impl.emulator.twoplayer

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.IOException
import java.io.InputStream

class TwoPlayerSaveFilesTest {
    @get:Rule val temporaryFolder = TemporaryFolder()
    private fun saves() = TwoPlayerSaveFiles(temporaryFolder.newFolder())

    @Test fun importedSaveUsesIndependentPersistentFile() {
        val files = saves()
        val original = temporaryFolder.newFile("original.sav").apply { writeText("player two") }
        val result = files.prepare("rom", "player one".byteInputStream(), original.inputStream(), false)
        assertEquals("player two", result.readText())
        result.writeText("traded")
        assertEquals("player two", original.readText())
        assertEquals("player one", files.primaryBackup("rom").readText())
    }

    @Test fun continueReusesWorkingCopyWithoutReplacingIt() {
        val files = saves()
        val first = files.prepare("rom", "p1".byteInputStream(), "p2".byteInputStream(), false)
        first.writeText("trade progress")
        val continued = files.prepare("rom", "p1 next".byteInputStream(), null, false)
        assertEquals(first.canonicalPath, continued.canonicalPath)
        assertEquals("trade progress", continued.readText())
        assertEquals("p1 next", files.primaryBackup("rom").readText())
    }

    @Test fun newSavePreservesPriorPlayerTwoAndPrimaryBackup() {
        val files = saves()
        files.prepare("rom", "old primary".byteInputStream(), "old second".byteInputStream(), false)
        val fresh = files.prepare("rom", "new primary".byteInputStream(), null, true)
        assertEquals(0L, fresh.length())
        val backups = files.directory("rom").listFiles()!!.filter { it.extension == "bak" }.map { it.readText() }
        assertTrue("old primary" in backups)
        assertTrue("old second" in backups)
    }

    @Test fun distinctRomIdentitiesNeverShareFilesEvenWithSameName() {
        val files = saves()
        assertNotEquals(files.playerTwo("content://first/game.nds"), files.playerTwo("content://second/game.nds"))
        assertEquals(files.playerTwo("content://first/game.nds"), files.playerTwo("content://first/game.nds"))
        assertEquals(files.playerTwo("../../elsewhere").parentFile.parentFile, files.directory("rom").parentFile)
    }

    @Test fun failedImportPreservesExistingWorkingCopyAndBackup() {
        val files = saves()
        files.prepare("rom", "old primary".byteInputStream(), "old second".byteInputStream(), false)
        val broken = object : InputStream() { override fun read(): Int = throw IOException("provider revoked") }
        assertThrows(IOException::class.java) { files.prepare("rom", "new primary".byteInputStream(), broken, false) }
        assertEquals("old second", files.playerTwo("rom").readText())
        assertEquals("old primary", files.primaryBackup("rom").readText())
        assertFalse(files.directory("rom").listFiles()!!.any { it.extension == "tmp" })
    }

    @Test fun failedPrimaryReadLeavesBothExistingFilesUnchanged() {
        val files = saves()
        files.prepare("rom", "primary".byteInputStream(), "second".byteInputStream(), false)
        val broken = object : InputStream() { override fun read(): Int = throw IOException("provider offline") }
        assertThrows(IOException::class.java) { files.prepare("rom", broken, "replacement".byteInputStream(), false) }
        assertEquals("second", files.playerTwo("rom").readText())
        assertEquals("primary", files.primaryBackup("rom").readText())
    }

    @Test fun emptyImportIsRejectedButBlankNewSaveIsAllowed() {
        val files = saves()
        assertThrows(IOException::class.java) { files.prepare("rom", byteArrayOf().inputStream(), byteArrayOf().inputStream(), false) }
        assertFalse(files.playerTwo("rom").exists())
        assertEquals(0L, files.prepare("rom", byteArrayOf().inputStream(), null, true).length())
    }

    @Test fun oversizedImportIsRejectedWithoutReplacingFiles() {
        val files = saves()
        files.prepare("rom", "primary".byteInputStream(), "second".byteInputStream(), false)
        val oversized = object : InputStream() {
            private var remaining = TwoPlayerSaveFiles.MAX_SAVE_BYTES + 1
            override fun read(): Int = if (remaining-- > 0) 0 else -1
            override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                if (remaining <= 0) return -1
                val count = minOf(length.toLong(), remaining).toInt()
                remaining -= count
                buffer.fill(0, offset, offset + count)
                return count
            }
        }
        assertThrows(IOException::class.java) { files.prepare("rom", "new primary".byteInputStream(), oversized, false) }
        assertEquals("second", files.playerTwo("rom").readText())
        assertEquals("primary", files.primaryBackup("rom").readText())
        assertFalse(files.directory("rom").listFiles()!!.any { it.extension == "tmp" })
    }

    @Test fun continueWithoutWorkingCopyFailsWithoutCreatingBackup() {
        val files = saves()
        assertThrows(IOException::class.java) { files.prepare("missing", "primary".byteInputStream(), null, false) }
        assertFalse(files.primaryBackup("missing").exists())
    }
}
