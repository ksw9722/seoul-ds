package me.magnum.melonds.impl.emulator

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.system.Os
import android.system.ErrnoException
import androidx.documentfile.provider.DocumentFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import me.magnum.melonds.MelonEmulator
import me.magnum.melonds.common.PermissionHandler
import me.magnum.melonds.common.romprocessors.RomFileProcessorFactory
import me.magnum.melonds.common.runtime.ScreenshotFrameBufferProvider
import me.magnum.melonds.domain.model.Cheat
import me.magnum.melonds.domain.model.ConsoleType
import me.magnum.melonds.domain.model.EmulatorConfiguration
import me.magnum.melonds.domain.model.MicSource
import me.magnum.melonds.domain.model.VideoRenderer
import me.magnum.melonds.domain.model.twoplayer.TwoPlayerSaveInfo
import me.magnum.melonds.domain.model.twoplayer.TwoPlayerStartResult
import me.magnum.melonds.impl.emulator.twoplayer.TwoPlayerSaveFiles
import java.io.File
import java.io.IOException
import me.magnum.melonds.domain.model.emulator.EmulatorEvent
import me.magnum.melonds.domain.model.emulator.FirmwareLaunchResult
import me.magnum.melonds.domain.model.emulator.RomLaunchResult
import me.magnum.melonds.domain.model.retroachievements.GameAchievementData
import me.magnum.melonds.domain.model.retroachievements.RAEvent
import me.magnum.melonds.domain.model.rom.Rom
import me.magnum.melonds.domain.model.rom.config.RomGbaSlotConfig
import me.magnum.melonds.domain.model.rom.config.RuntimeConsoleType
import me.magnum.melonds.domain.model.rom.config.RuntimeEnum
import me.magnum.melonds.domain.repositories.SettingsRepository
import me.magnum.melonds.domain.services.EmulatorManager
import me.magnum.melonds.impl.camera.DSiCameraSourceMultiplexer
import me.magnum.melonds.ui.emulator.rewind.model.RewindSaveState
import me.magnum.melonds.ui.emulator.rewind.model.RewindWindow

class AndroidEmulatorManager(
    private val context: Context,
    private val settingsRepository: SettingsRepository,
    private val sramProvider: SramProvider,
    private val screenshotFrameBufferProvider: ScreenshotFrameBufferProvider,
    private val romFileProcessorFactory: RomFileProcessorFactory,
    private val permissionHandler: PermissionHandler,
    private val cameraManager: DSiCameraSourceMultiplexer,
) : EmulatorManager {

    // Native state transitions and teardown may wait for I/O/frame boundaries. Never block the UI.
    private val stateDispatcher = Dispatchers.IO.limitedParallelism(1)
    private val twoPlayerSaves = TwoPlayerSaveFiles(File(context.filesDir, "two-player"))
    private var loadedRomIdentity: Uri? = null
    private var loadedRomUri: Uri? = null
    private var loadedSaveUri: Uri? = null
    private var loadedConfiguration: EmulatorConfiguration? = null

    private val _emulatorEvents = MutableSharedFlow<EmulatorEvent>(extraBufferCapacity = Int.MAX_VALUE)
    override val emulatorEvents: Flow<EmulatorEvent> = _emulatorEvents.asSharedFlow()

    private val achievementsSharedFlow = MutableSharedFlow<RAEvent>(replay = 0, extraBufferCapacity = Int.MAX_VALUE)

    private val messageQueue = EmulatorMessageQueue { type, data ->
        when (type) {
            EmulatorEventType.EventRumbleStart -> _emulatorEvents.tryEmit(EmulatorEvent.RumbleStart(data.getInt()))
            EmulatorEventType.EventRumbleStop -> _emulatorEvents.tryEmit(EmulatorEvent.RumbleStop)
            EmulatorEventType.EventEmulatorStop -> getStopReason(data.getInt())?.let { _emulatorEvents.tryEmit(EmulatorEvent.Stop(it)) }
            EmulatorEventType.EventRAAchievementPrimed -> achievementsSharedFlow.tryEmit(RAEvent.OnAchievementPrimed(data.getLong()))
            EmulatorEventType.EventRAAchievementTriggered -> achievementsSharedFlow.tryEmit(RAEvent.OnAchievementTriggered(data.getLong()))
            EmulatorEventType.EventRAAchievementUnprimed -> achievementsSharedFlow.tryEmit(RAEvent.OnAchievementUnPrimed(data.getLong()))
            EmulatorEventType.EventRAAchievementProgressUpdated -> {
                val event = RAEvent.OnAchievementProgressUpdated(
                    achievementId = data.getLong(),
                    current = data.getInt(),
                    target = data.getInt(),
                    progress = String(ByteArray(data.getInt()).apply { data.get(this) }),
                )
                achievementsSharedFlow.tryEmit(event)
            }
            EmulatorEventType.EventRALeaderboardAttemptStarted -> achievementsSharedFlow.tryEmit(RAEvent.OnLeaderboardAttemptStarted(data.getLong()))
            EmulatorEventType.EventRALeaderboardAttemptUpdated -> {
                val event = RAEvent.OnLeaderboardAttemptUpdated(
                    leaderboardId = data.getLong(),
                    formattedValue = String(ByteArray(data.getInt()).apply { data.get(this) }),
                )
                achievementsSharedFlow.tryEmit(event)
            }
            EmulatorEventType.EventRALeaderboardAttemptCanceled -> achievementsSharedFlow.tryEmit(RAEvent.OnLeaderboardAttemptCancelled(data.getLong()))
            EmulatorEventType.EventRALeaderboardAttemptCompleted -> {
                val event = RAEvent.OnLeaderboardAttemptCompleted(
                    leaderboardId = data.getLong(),
                    value = data.getInt(),
                    formattedValue = String(ByteArray(data.getInt()).apply { data.get(this) }),
                )
                achievementsSharedFlow.tryEmit(event)
            }
        }
    }

    override suspend fun loadRom(rom: Rom, cheats: List<Cheat>): RomLaunchResult {
        return withContext(stateDispatcher) {
            val fileRomDocument = DocumentFile.fromSingleUri(context, rom.uri) ?: return@withContext RomLaunchResult.LaunchFailedRomNotFound
            val fileRomProcessor = romFileProcessorFactory.getFileRomProcessorForDocument(fileRomDocument)
            val romUri = fileRomProcessor?.getRealRomUri(rom) ?: return@withContext RomLaunchResult.LaunchFailedRomNotSupported

            val configuration = getRomEmulatorConfiguration(rom)
            setupEmulator(configuration)

            val sram = try {
                sramProvider.getSramForRom(rom)
            } catch (exception: SramLoadException) {
                return@withContext RomLaunchResult.LaunchFailedSramProblem(exception)
            }

            val gbaSlotRomConfig = rom.config.gbaSlotConfig
            val gbaSlotType = when (gbaSlotRomConfig) {
                RomGbaSlotConfig.None -> MelonEmulator.GbaSlotType.NONE
                is RomGbaSlotConfig.GbaRom -> MelonEmulator.GbaSlotType.GBA_ROM
                RomGbaSlotConfig.MemoryExpansion -> MelonEmulator.GbaSlotType.MEMORY_EXPANSION
                RomGbaSlotConfig.RumblePak -> MelonEmulator.GbaSlotType.RUMBLE_PAK
            }

            val loadResult = MelonEmulator.loadRom(
                romUri = romUri,
                sramUri = sram,
                gbaSlotType = gbaSlotType,
                gbaRomUri = (gbaSlotRomConfig as? RomGbaSlotConfig.GbaRom)?.romPath,
                gbaSramUri = (gbaSlotRomConfig as? RomGbaSlotConfig.GbaRom)?.savePath
            )
            if (loadResult.isTerminal || !isActive) {
                cameraManager.stopCurrentCameraSource()
                MelonEmulator.stopEmulation()
                RomLaunchResult.LaunchFailed(loadResult)
            } else {
                loadedRomIdentity = rom.uri
                loadedRomUri = romUri
                loadedSaveUri = sram
                loadedConfiguration = configuration
                messageQueue.start()
                MelonEmulator.setupCheats(cheats.toTypedArray())
                MelonEmulator.startEmulation()

                RomLaunchResult.LaunchSuccessful(loadResult != MelonEmulator.LoadResult.SUCCESS_GBA_FAILED)
            }
        }
    }

    override suspend fun getTwoPlayerSaveInfo(rom: Rom) = withContext(stateDispatcher) {
        TwoPlayerSaveInfo(twoPlayerSaves.playerTwo(rom.uri.toString()).isFile, twoPlayerSaves.primaryBackup(rom.uri.toString()).isFile)
    }

    override suspend fun startSecondPlayer(rom: Rom, importedSave: Uri?, createNew: Boolean): TwoPlayerStartResult = withContext(stateDispatcher) {
        val romUri = loadedRomUri
        val primarySave = loadedSaveUri
        val configuration = loadedConfiguration
        if (romUri == null || primarySave == null || loadedRomIdentity != rom.uri || MelonEmulator.isTwoPlayerActive()) {
            return@withContext TwoPlayerStartResult.INVALID_SESSION
        }
        if (configuration == null || configuration.consoleType != ConsoleType.DS || configuration.rendererConfiguration.renderer != VideoRenderer.SOFTWARE || rom.isDsiWareTitle) {
            return@withContext TwoPlayerStartResult.UNSUPPORTED_CONFIGURATION
        }
        try {
            if (importedSave != null && sameDocument(importedSave, primarySave)) return@withContext TwoPlayerStartResult.SAME_SAVE
            // Serialized with teardown; pause flushes SRAM before backing it up or exporting it.
            MelonEmulator.pauseEmulation()
            if (!MelonEmulator.flushSaveFiles()) return@withContext TwoPlayerStartResult.SAVE_ERROR
            val primary = context.contentResolver.openInputStream(primarySave) ?: throw IOException("Cannot read primary save")
            val secondary = primary.use {
                val imported = importedSave?.let { uri -> context.contentResolver.openInputStream(uri) ?: throw IOException("Cannot read second save") }
                imported.use { twoPlayerSaves.prepare(rom.uri.toString(), primary, imported, createNew) }
            }
            when (MelonEmulator.startSecondPlayer(romUri, Uri.fromFile(secondary))) {
                0 -> TwoPlayerStartResult.SUCCESS
                1 -> TwoPlayerStartResult.INVALID_SESSION
                2 -> TwoPlayerStartResult.UNSUPPORTED_CONFIGURATION
                3 -> TwoPlayerStartResult.SAVE_ERROR
                else -> TwoPlayerStartResult.START_FAILED
            }
        } catch (_: IOException) {
            TwoPlayerStartResult.SAVE_ERROR
        } catch (_: SecurityException) {
            TwoPlayerStartResult.SAVE_ERROR
        }
    }

    override suspend fun selectPlayer(index: Int): Boolean = withContext(stateDispatcher) {
        MelonEmulator.pauseEmulation()
        MelonEmulator.selectPlayer(index)
    }

    override suspend fun exportTwoPlayerSave(rom: Rom, destination: Uri, primaryBackup: Boolean): Boolean = withContext(stateDispatcher) {
        try {
            // Reject known aliases of the live primary save and source ROM before opening output.
            if (loadedSaveUri?.let { sameDocument(it, destination) } == true || loadedRomUri?.let { sameDocument(it, destination) } == true) return@withContext false
            MelonEmulator.pauseEmulation()
            if (!MelonEmulator.flushSaveFiles()) return@withContext false
            val source = if (primaryBackup) twoPlayerSaves.primaryBackup(rom.uri.toString()) else twoPlayerSaves.playerTwo(rom.uri.toString())
            if (!source.isFile || sameDocument(Uri.fromFile(source), destination)) return@withContext false
            source.inputStream().use { input ->
                (context.contentResolver.openOutputStream(destination, "wt") ?: throw IOException("Cannot export save")).use { output ->
                    input.copyTo(output)
                    output.flush()
                }
            }
            true
        } catch (_: IOException) {
            false
        } catch (_: SecurityException) {
            false
        }
    }

    private fun sameDocument(first: Uri, second: Uri): Boolean {
        if (first.normalizeScheme() == second.normalizeScheme()) return true
        if (first.scheme == "file" && second.scheme == "file") return File(first.path!!).canonicalFile == File(second.path!!).canonicalFile
        if (first.authority == second.authority && DocumentsContract.isDocumentUri(context, first) && DocumentsContract.isDocumentUri(context, second)) {
            if (DocumentsContract.getDocumentId(first) == DocumentsContract.getDocumentId(second)) return true
        }
        // URI aliases can cross SAF authorities (or file:// and content://). Compare the actual
        // open file when providers expose one, without ever opening a candidate for writing.
        return try {
            context.contentResolver.openFileDescriptor(first, "r")?.use { firstDescriptor ->
                context.contentResolver.openFileDescriptor(second, "r")?.use { secondDescriptor ->
                    val firstStat = Os.fstat(firstDescriptor.fileDescriptor)
                    val secondStat = Os.fstat(secondDescriptor.fileDescriptor)
                    firstStat.st_dev == secondStat.st_dev && firstStat.st_ino == secondStat.st_ino
                } ?: false
            } ?: false
        } catch (_: IOException) {
            false
        } catch (_: SecurityException) {
            false
        } catch (_: ErrnoException) {
            false
        }
    }

    override suspend fun loadFirmware(consoleType: ConsoleType): FirmwareLaunchResult {
        return withContext(stateDispatcher) {
            setupEmulator(getFirmwareEmulatorConfiguration(consoleType))
            val result = MelonEmulator.bootFirmware()
            if (result != MelonEmulator.FirmwareLoadResult.SUCCESS) {
                cameraManager.stopCurrentCameraSource()
                MelonEmulator.stopEmulation()
                FirmwareLaunchResult.LaunchFailed(result)
            } else {
                messageQueue.start()
                MelonEmulator.startEmulation()
                FirmwareLaunchResult.LaunchSuccessful
            }
        }
    }

    override suspend fun updateRomEmulatorConfiguration(rom: Rom) = withContext(stateDispatcher) {
        if (MelonEmulator.isTwoPlayerActive()) return@withContext
        val configuration = getRomEmulatorConfiguration(rom)
        MelonEmulator.updateEmulatorConfiguration(configuration)
        // Changing a preference does not recreate the already booted DS/DSi hardware.
        loadedConfiguration = configuration.copy(consoleType = loadedConfiguration?.consoleType ?: configuration.consoleType)
    }

    override suspend fun updateFirmwareEmulatorConfiguration(consoleType: ConsoleType) = withContext(stateDispatcher) {
        val configuration = getFirmwareEmulatorConfiguration(consoleType)
        MelonEmulator.updateEmulatorConfiguration(configuration)
    }

    override suspend fun getRewindWindow(): RewindWindow {
        return MelonEmulator.getRewindWindow()
    }

    override fun getFps(): Float {
        return MelonEmulator.getFPS()
    }

    override suspend fun pauseEmulator() = withContext(stateDispatcher) {
        MelonEmulator.pauseEmulation()
    }

    override suspend fun resumeEmulator() = withContext(stateDispatcher) {
        MelonEmulator.resumeEmulation()
    }

    override suspend fun resetEmulator() = withContext(stateDispatcher) {
        MelonEmulator.resetEmulation()
    }

    override suspend fun updateCheats(cheats: List<Cheat>) = withContext(stateDispatcher) {
        if (MelonEmulator.isTwoPlayerActive()) return@withContext
        MelonEmulator.setupCheats(cheats.toTypedArray())
    }

    override suspend fun setupRetroAchievements(achievementData: GameAchievementData) = withContext(stateDispatcher) {
        if (MelonEmulator.isTwoPlayerActive()) return@withContext
        val richPresencePath = if (settingsRepository.isRetroAchievementsRichPresenceEnabled()) {
            achievementData.richPresencePatch
        } else {
            null
        }

        MelonEmulator.setupAchievements(
            achievements = achievementData.lockedAchievements.toTypedArray(),
            leaderboards = achievementData.leaderboards.toTypedArray(),
            richPresenceScript = richPresencePath,
        )
    }

    override suspend fun unloadRetroAchievementsData() = withContext(stateDispatcher) {
        MelonEmulator.unloadRetroAchievementsData()
    }

    override suspend fun loadRewindState(rewindSaveState: RewindSaveState): Boolean = withContext(stateDispatcher) {
        MelonEmulator.loadRewindState(rewindSaveState)
    }

    override suspend fun saveState(saveStateFileUri: Uri): Boolean = withContext(stateDispatcher) {
        MelonEmulator.saveState(saveStateFileUri)
    }

    override suspend fun loadState(saveStateFileUri: Uri): Boolean = withContext(stateDispatcher) {
        MelonEmulator.loadState(saveStateFileUri)
    }

    override suspend fun takeScreenshot(): Boolean = withContext(Dispatchers.IO) {
        MelonEmulator.takeScreenshot()
    }

    override suspend fun stopEmulator() = withContext(stateDispatcher) {
        MelonEmulator.stopEmulation()
        loadedRomIdentity = null
        loadedRomUri = null
        loadedSaveUri = null
        loadedConfiguration = null
        cameraManager.stopCurrentCameraSource()
        messageQueue.stop()
    }

    override fun cleanEmulator() {
        cameraManager.dispose()
        messageQueue.cleanup()
    }

    override fun observeRetroAchievementEvents(): Flow<RAEvent> {
        return achievementsSharedFlow.asSharedFlow()
    }

    private fun setupEmulator(emulatorConfiguration: EmulatorConfiguration) {
        MelonEmulator.setupEmulator(
            emulatorConfiguration = emulatorConfiguration,
            dsiCameraSource = cameraManager,
            screenshotBuffer = screenshotFrameBufferProvider.frameBuffer(),
        )
    }

    private suspend fun getRomEmulatorConfiguration(rom: Rom): EmulatorConfiguration {
        val baseConfiguration = settingsRepository.getEmulatorConfiguration()
        val mustUseCustomBios = baseConfiguration.useCustomBios || rom.config.runtimeConsoleType != RuntimeConsoleType.DEFAULT
        return baseConfiguration.copy(
            useCustomBios = mustUseCustomBios,
            showBootScreen = baseConfiguration.showBootScreen && mustUseCustomBios,
            consoleType = getRomOptionOrDefault(rom.config.runtimeConsoleType, baseConfiguration.consoleType),
            micSource = getRomOptionOrDefault(rom.config.runtimeMicSource, baseConfiguration.micSource)
        ).run { getPermissionAdjustedConfiguration(this) }
    }

    private suspend fun getFirmwareEmulatorConfiguration(consoleType: ConsoleType): EmulatorConfiguration {
        return settingsRepository.getEmulatorConfiguration().copy(
            consoleType = consoleType,
            useCustomBios = true,
            showBootScreen = true,
        ).run { getPermissionAdjustedConfiguration(this) }
    }

    private fun <T, U> getRomOptionOrDefault(romOption: T, default: U): U where T : RuntimeEnum<T, U> {
        return if (romOption.getDefault() == romOption) {
            default
        } else {
            romOption.getValue()
        }
    }

    private suspend fun getPermissionAdjustedConfiguration(originalConfiguration: EmulatorConfiguration): EmulatorConfiguration {
        if (originalConfiguration.micSource == MicSource.DEVICE) {
            if (!permissionHandler.checkPermission(android.Manifest.permission.RECORD_AUDIO)) {
                return originalConfiguration.copy(micSource = MicSource.NONE)
            }
        }

        return originalConfiguration
    }

    private fun getStopReason(internalReason: Int): EmulatorEvent.Stop.Reason? {
        return when (internalReason) {
            Unknown -> EmulatorEvent.Stop.Reason.InternalError
            GBAModeNotSupported -> EmulatorEvent.Stop.Reason.GBAModeNotSupported
            BadExceptionRegion -> EmulatorEvent.Stop.Reason.BadExceptionRegion
            PowerOff -> EmulatorEvent.Stop.Reason.PowerOff
            else -> null
        }
    }

    /**
     * The values of the different stop reasons, as defined in the emulator's core (in `melonDS::Platform::StopReason`)
     */
    companion object InternalStopReason {
        private const val Unknown = 0
        private const val GBAModeNotSupported = 2
        private const val BadExceptionRegion = 3
        private const val PowerOff = 4
    }
}