package me.magnum.melonds.ui.setup

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import me.magnum.melonds.domain.model.ConsoleType
import me.magnum.melonds.domain.repositories.SettingsRepository
import me.magnum.melonds.ui.settings.SettingsActivity
import me.magnum.melonds.ui.theme.MelonTheme
import javax.inject.Inject

@AndroidEntryPoint
class SetupActivity : AppCompatActivity() {
    @Inject lateinit var settingsRepository: SettingsRepository

    private var status by mutableStateOf<SetupStatus?>(null)
    private var statusUnavailable by mutableStateOf(false)
    private var refreshJob: Job? = null
    private var navigating = false

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            navigationBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        setContent {
            MelonTheme {
                SetupScreen(
                    status = status,
                    statusUnavailable = statusUnavailable,
                    onBack = { finish() },
                    onOpenFolders = { openSettings(SettingsActivity.ROMS_ENTRY_POINT) },
                    onOpenFirmware = { openSettings(SettingsActivity.CUSTOM_FIRMWARE_ENTRY_POINT) },
                    onOpenSaves = { openSettings(SettingsActivity.SAVE_FILES_ENTRY_POINT) },
                    onOpenSystem = { openSettings(SettingsActivity.SYSTEM_ENTRY_POINT) },
                    onContinue = ::finishGuide,
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        navigating = false
        refreshStatus()
    }

    private fun openSettings(entryPoint: String) {
        // Ignore repeated taps while the next activity is being opened.
        if (navigating) return
        navigating = true
        startActivity(Intent(this, SettingsActivity::class.java).apply {
            putExtra(SettingsActivity.KEY_ENTRY_POINT, entryPoint)
        })
    }

    private fun finishGuide() {
        if (navigating) return
        navigating = true
        SetupGuidePreferences.markReviewed(this)
        finish()
    }

    private fun refreshStatus() {
        refreshJob?.cancel()
        refreshJob = lifecycleScope.launch {
            try {
                val latest = withContext(Dispatchers.IO) {
                    val directories = settingsRepository.getRomSearchDirectories().toSet()
                    val permissions = contentResolver.persistedUriPermissions.associateBy { it.uri }
                    SetupStatus(
                        directoryCount = directories.size,
                        readableDirectoryCount = directories.count { permissions[it]?.isReadPermission == true },
                        writableDirectoryCount = directories.count {
                            permissions[it]?.let { permission -> permission.isReadPermission && permission.isWritePermission } == true
                        },
                        isDsMode = settingsRepository.getDefaultConsoleType() == ConsoleType.DS,
                        usesCustomBios = settingsRepository.useCustomBios(),
                        showsBootScreen = settingsRepository.showBootScreen(),
                        savesNextToRom = settingsRepository.saveNextToRomFile(),
                        hasSeparateSaveDirectory = settingsRepository.getSaveFileDirectory() != null,
                        jitEnabled = settingsRepository.isJitEnabled(),
                    )
                }
                status = latest
                statusUnavailable = false
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Some document providers or restored preferences can fail.
                // Keep the guide and its recovery actions usable, without
                // logging user folder paths or claiming stale status is current.
                status = null
                statusUnavailable = true
            }
        }
    }
}
