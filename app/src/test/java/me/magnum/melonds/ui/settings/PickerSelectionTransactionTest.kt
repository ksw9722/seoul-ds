package me.magnum.melonds.ui.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class PickerSelectionTransactionTest {
    @Test fun cancelledPickerDoesNotValidatePersistOrChangeSelection() {
        val result = PickerSelectionTransaction.execute<String>(
            selection = null,
            prepare = { fail("Cancelled picker prepared access"); true },
            commit = { fail("Cancelled picker changed selection") },
        )
        assertEquals(PickerSelectionTransaction.Result.CANCELLED, result)
    }

    @Test fun failedValidationPreservesExistingSelection() {
        var selected = "previous"
        val result = PickerSelectionTransaction.execute("new", prepare = { false }, commit = { selected = it })
        assertEquals("previous", selected)
        assertEquals(PickerSelectionTransaction.Result.REJECTED, result)
    }

    @Test fun refusedPersistableGrantPreservesExistingSelection() {
        var selected = "previous"
        val result = PickerSelectionTransaction.execute(
            "new",
            prepare = { throw SecurityException("Provider refused persistent access") },
            commit = { selected = it },
        )
        assertEquals("previous", selected)
        assertEquals(PickerSelectionTransaction.Result.REJECTED, result)
    }

    @Test fun malformedProviderUriPreservesExistingSelection() {
        var selected = "previous"
        val result = PickerSelectionTransaction.execute(
            "new",
            prepare = { throw IllegalArgumentException("Invalid tree URI") },
            commit = { selected = it },
        )
        assertEquals("previous", selected)
        assertEquals(PickerSelectionTransaction.Result.REJECTED, result)
    }

    @Test fun successfulGrantIsAcquiredBeforePreferenceChanges() {
        val events = mutableListOf<String>()
        val result = PickerSelectionTransaction.execute(
            "new",
            prepare = { events += "validate"; events += "persist grant"; true },
            commit = { events += "save selection" },
        )
        assertEquals(listOf("validate", "persist grant", "save selection"), events)
        assertEquals(PickerSelectionTransaction.Result.COMMITTED, result)
    }

    @Test(expected = IllegalArgumentException::class)
    fun preferenceCommitErrorIsNotHiddenAsProviderDenial() {
        PickerSelectionTransaction.execute("new", prepare = { true }, commit = { throw IllegalArgumentException("Commit error") })
    }
}
