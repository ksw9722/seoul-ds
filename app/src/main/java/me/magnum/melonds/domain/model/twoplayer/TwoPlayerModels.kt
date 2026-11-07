package me.magnum.melonds.domain.model.twoplayer

data class TwoPlayerSaveInfo(val hasPlayerTwoSave: Boolean, val hasPrimaryBackup: Boolean)

enum class TwoPlayerStartResult {
    SUCCESS, INVALID_SESSION, UNSUPPORTED_CONFIGURATION, SAVE_ERROR, START_FAILED, SAME_SAVE,
}
