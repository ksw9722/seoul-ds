package me.magnum.melonds.ui.setup

import android.content.Context
import androidx.core.content.edit

/** Separate from emulator settings: dismissing the guide never changes gameplay configuration. */
object SetupGuidePreferences {
    private const val PREFERENCES = "seoul_ds_setup_guide"
    private const val COMPLETED_VERSION = "completed_version"

    fun shouldShowAutomatically(context: Context, restoringActivity: Boolean): Boolean {
        val completedVersion = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .getInt(COMPLETED_VERSION, 0)
        return SetupGuidePolicy.shouldShowAutomatically(completedVersion, restoringActivity)
    }

    fun markReviewed(context: Context) {
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .edit {
                putInt(COMPLETED_VERSION, SetupGuidePolicy.CURRENT_VERSION)
            }
    }
}
