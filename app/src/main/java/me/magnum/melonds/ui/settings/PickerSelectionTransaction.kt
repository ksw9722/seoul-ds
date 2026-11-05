package me.magnum.melonds.ui.settings

/**
 * Prepares access before changing a persisted selection. Provider validation and
 * grant failures must not replace the last working file/folder preference.
 * Commit failures are intentionally not reclassified as permission failures.
 */
internal object PickerSelectionTransaction {
    enum class Result { CANCELLED, REJECTED, COMMITTED }

    fun <T : Any> execute(selection: T?, prepare: (T) -> Boolean, commit: (T) -> Unit): Result {
        if (selection == null) return Result.CANCELLED

        val ready = try {
            prepare(selection)
        } catch (_: SecurityException) {
            false
        } catch (_: IllegalArgumentException) {
            false
        }

        if (!ready) return Result.REJECTED
        commit(selection)
        return Result.COMMITTED
    }
}
