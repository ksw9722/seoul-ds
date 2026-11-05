package me.magnum.melonds.ui.emulator.savestate

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import kotlinx.coroutines.sync.Mutex
import me.magnum.melonds.ui.emulator.exceptions.SaveSlotLoadException
import java.io.IOException

/**
 * Single-flight state operations. Calls and lifecycle requests belong to the UI dispatcher.
 *
 * A save finishing must not undo a later lifecycle/menu pause. Cancellation is deliberately not
 * converted into a storage failure, and never resumes a session which is being destroyed.
 */
internal class SaveStateOperationCoordinator {
    private val mutex = Mutex()
    private var resumeRequested = false

    val isRunning: Boolean get() = mutex.isLocked

    fun requestPause() {
        resumeRequested = false
    }

    fun requestResume() {
        resumeRequested = true
    }

    suspend fun run(
        pause: suspend () -> Unit,
        operation: suspend () -> Boolean,
        onResult: suspend (Boolean) -> Unit,
        resume: suspend () -> Unit,
    ): Boolean {
        // Do not queue repeated controller taps or let saves and loads overlap.
        if (!mutex.tryLock()) return false

        var cancelled = false
        try {
            pause()
            val succeeded = recoverStorageFailure(operation)
            onResult(succeeded)
        } catch (exception: CancellationException) {
            cancelled = true
            throw exception
        } finally {
            mutex.unlock()
            if (!cancelled && currentCoroutineContext().isActive && resumeRequested) {
                resume()
            }
        }
        return true
    }
}

/** Only expected document/storage errors are recoverable; programming errors remain visible. */
internal suspend fun recoverStorageFailure(operation: suspend () -> Boolean): Boolean {
    return try {
        operation()
    } catch (_: SaveSlotLoadException) {
        false
    } catch (_: IOException) {
        false
    } catch (_: SecurityException) {
        false
    }
}
