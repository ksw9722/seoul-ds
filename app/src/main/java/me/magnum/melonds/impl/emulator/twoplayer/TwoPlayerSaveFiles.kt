package me.magnum.melonds.impl.emulator.twoplayer

import java.io.File
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID

/** Persistent, per-ROM working copies. Imported documents are read, never opened for writing. */
internal class TwoPlayerSaveFiles(private val root: File) {
    companion object {
        // Reject accidental ROMs/archives and unbounded document providers before consuming storage.
        const val MAX_SAVE_BYTES = 64L * 1024 * 1024
    }

    fun directory(romIdentity: String): File {
        val key = MessageDigest.getInstance("SHA-256").digest(romIdentity.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        return File(root, key)
    }

    fun playerTwo(romIdentity: String) = File(directory(romIdentity), "player2.sav")
    fun primaryBackup(romIdentity: String) = File(directory(romIdentity), "player1-before-2p.sav")

    fun prepare(romIdentity: String, primary: InputStream, imported: InputStream?, createNew: Boolean): File {
        val directory = directory(romIdentity)
        if (!directory.isDirectory && !directory.mkdirs()) throw IOException("Cannot create 2P save directory")
        val target = playerTwo(romIdentity)
        if (!createNew && imported == null && !target.isFile) throw IOException("No saved player two session")

        // First stage all input. A failed read must not truncate either working save or old backup.
        val primaryStaged = stage(directory, primary, allowEmpty = true)
        var secondStaged: File? = null
        try {
            secondStaged = when {
                imported != null -> stage(directory, imported, allowEmpty = false)
                createNew -> stage(directory, ByteArray(0).inputStream(), allowEmpty = true)
                else -> null
            }
            preserve(primaryBackup(romIdentity))
            install(primaryStaged, primaryBackup(romIdentity))
            if (secondStaged != null) {
                preserve(target)
                install(secondStaged, target)
            }
            return target
        } finally {
            primaryStaged.delete()
            secondStaged?.delete()
        }
    }

    private fun preserve(file: File) {
        if (file.isFile) {
            val backup = File(file.parentFile, "${file.name}.${UUID.randomUUID()}.bak")
            file.copyTo(backup, overwrite = false)
        }
    }

    private fun install(staged: File, destination: File) {
        // Both files are on the same app-private filesystem: rename replaces atomically on Android.
        if (!staged.renameTo(destination)) throw IOException("Could not install 2P save copy")
    }

    private fun stage(directory: File, input: InputStream, allowEmpty: Boolean): File {
        val staged = File.createTempFile("import-", ".tmp", directory)
        try {
            var total = 0L
            staged.outputStream().use { output ->
                input.use { source ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    while (true) {
                        val count = source.read(buffer)
                        if (count < 0) break
                        total += count
                        if (total > MAX_SAVE_BYTES) throw IOException("Save file is too large")
                        output.write(buffer, 0, count)
                    }
                }
                if (!allowEmpty && total == 0L) throw IOException("Selected save is empty")
                output.fd.sync()
            }
            return staged
        } catch (error: Throwable) {
            staged.delete()
            throw error
        }
    }
}
