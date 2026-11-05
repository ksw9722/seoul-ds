package me.magnum.melonds.ui.emulator.savestate

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import me.magnum.melonds.ui.emulator.exceptions.SaveSlotLoadException
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException

class SaveStateOperationCoordinatorTest {
    @Test
    fun successfulOperationPausesThenReportsThenResumes() = runBlocking {
        val coordinator = SaveStateOperationCoordinator().apply { requestResume() }
        val calls = mutableListOf<String>()
        assertTrue(coordinator.run(
            pause = { calls += "pause" },
            operation = { calls += "save"; true },
            onResult = { calls += "result:$it" },
            resume = { calls += "resume" },
        ))
        assertEquals(listOf("pause", "save", "result:true", "resume"), calls)
        assertFalse(coordinator.isRunning)
    }

    @Test
    fun laterLifecyclePauseWinsOverCompletion() = runBlocking {
        val coordinator = SaveStateOperationCoordinator().apply { requestResume() }
        var resumed = false
        coordinator.run({}, { coordinator.requestPause(); true }, {}, { resumed = true })
        assertFalse(resumed)
    }

    @Test
    fun resumeRequestedDuringOperationIsAppliedAtCompletion() = runBlocking {
        val coordinator = SaveStateOperationCoordinator()
        var resumed = false
        coordinator.run({}, { coordinator.requestResume(); true }, {}, { resumed = true })
        assertTrue(resumed)
    }

    @Test
    fun duplicateTapIsDroppedInsteadOfOverlappingOrQueuing() = runBlocking {
        val coordinator = SaveStateOperationCoordinator()
        val release = CompletableDeferred<Unit>()
        var operations = 0
        val first = launch(start = CoroutineStart.UNDISPATCHED) {
            coordinator.run({}, { operations++; release.await(); true }, {}, {})
        }
        assertTrue(coordinator.isRunning)
        assertFalse(coordinator.run({}, { operations++; true }, {}, {}))
        release.complete(Unit)
        first.join()
        assertEquals(1, operations)
        assertFalse(coordinator.isRunning)
    }

    @Test
    fun storageErrorsReportFailureAndAllowAnotherAttempt() = runBlocking {
        val failures = listOf(IOException("full"), SecurityException("revoked"), SaveSlotLoadException("missing"))
        for (failure in failures) {
            val coordinator = SaveStateOperationCoordinator().apply { requestResume() }
            var reported: Boolean? = null
            var resumed = false
            coordinator.run({}, { throw failure }, { reported = it }, { resumed = true })
            assertEquals(false, reported)
            assertTrue(resumed)
            assertFalse(coordinator.isRunning)
            assertTrue(coordinator.run({}, { true }, {}, {}))
        }
    }

    @Test
    fun falseNativeResultIsNotReportedAsSuccess() = runBlocking {
        val coordinator = SaveStateOperationCoordinator()
        var reported: Boolean? = null
        coordinator.run({}, { false }, { reported = it }, {})
        assertEquals(false, reported)
    }

    @Test
    fun cancellationReleasesGateWithoutResumingOrReportingFailure() = runBlocking {
        val coordinator = SaveStateOperationCoordinator().apply { requestResume() }
        val wait = CompletableDeferred<Unit>()
        var reported = false
        var resumed = false
        val job = launch(start = CoroutineStart.UNDISPATCHED) {
            coordinator.run({}, { wait.await(); true }, { reported = true }, { resumed = true })
        }
        job.cancelAndJoin()
        assertFalse(reported)
        assertFalse(resumed)
        assertFalse(coordinator.isRunning)
    }

    @Test
    fun explicitCancellationIsNeverSwallowedOrResumed() = runBlocking {
        val coordinator = SaveStateOperationCoordinator().apply { requestResume() }
        var resumed = false
        try {
            coordinator.run({}, { throw CancellationException("session ended") }, {}, { resumed = true })
            fail("Cancellation must propagate")
        } catch (_: CancellationException) {
            assertFalse(resumed)
            assertFalse(coordinator.isRunning)
        }
    }

    @Test
    fun programmingErrorsRemainVisibleAndGateIsReleased() = runBlocking {
        val coordinator = SaveStateOperationCoordinator()
        try {
            coordinator.run({}, { error("unexpected invariant failure") }, {}, {})
            fail("Programming error must not be masked")
        } catch (_: IllegalStateException) {
            assertFalse(coordinator.isRunning)
        }
    }
}
