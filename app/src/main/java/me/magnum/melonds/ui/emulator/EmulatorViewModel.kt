package me.magnum.melonds.ui.emulator

import android.net.Uri
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.flow.shareIn
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import me.magnum.melonds.MelonEmulator
import me.magnum.melonds.common.romprocessors.RomFileProcessorFactory
import me.magnum.melonds.common.runtime.ScreenshotFrameBufferProvider
import me.magnum.melonds.domain.model.Cheat
import me.magnum.melonds.domain.model.ConsoleType
import me.magnum.melonds.domain.model.FpsCounterPosition
import me.magnum.melonds.domain.model.RomInfo
import me.magnum.melonds.domain.model.RuntimeBackground
import me.magnum.melonds.domain.model.SaveStateSlot
import me.magnum.melonds.domain.model.emulator.EmulatorEvent
import me.magnum.melonds.domain.model.emulator.EmulatorSessionUpdateAction
import me.magnum.melonds.domain.model.emulator.FirmwareLaunchResult
import me.magnum.melonds.domain.model.emulator.RomLaunchResult
import me.magnum.melonds.domain.model.layout.BackgroundMode
import me.magnum.melonds.domain.model.layout.Insets
import me.magnum.melonds.domain.model.layout.LayoutConfiguration
import me.magnum.melonds.domain.model.layout.LayoutDisplayPair
import me.magnum.melonds.domain.model.layout.ScreenFold
import me.magnum.melonds.domain.model.retroachievements.GameAchievementData
import me.magnum.melonds.domain.model.retroachievements.RAEvent
import me.magnum.melonds.domain.model.retroachievements.RASimpleAchievement
import me.magnum.melonds.domain.model.retroachievements.RASimpleLeaderboard
import me.magnum.melonds.domain.model.rom.Rom
import me.magnum.melonds.domain.model.ui.Orientation
import me.magnum.melonds.domain.model.twoplayer.TwoPlayerStartResult
import me.magnum.melonds.domain.repositories.BackgroundRepository
import me.magnum.melonds.domain.repositories.CheatsRepository
import me.magnum.melonds.domain.repositories.LayoutsRepository
import me.magnum.melonds.domain.repositories.RetroAchievementsRepository
import me.magnum.melonds.domain.repositories.RomsRepository
import me.magnum.melonds.domain.repositories.SaveStatesRepository
import me.magnum.melonds.domain.repositories.SettingsRepository
import me.magnum.melonds.domain.services.EmulatorManager
import me.magnum.melonds.impl.emulator.EmulatorSession
import me.magnum.melonds.impl.layout.UILayoutProvider
import me.magnum.melonds.ui.emulator.component.RetroAchievementsSubmissionHandler
import me.magnum.melonds.ui.emulator.firmware.FirmwarePauseMenuOption
import me.magnum.melonds.ui.emulator.model.EmulatorState
import me.magnum.melonds.ui.emulator.model.EmulatorUiEvent
import me.magnum.melonds.ui.emulator.model.LaunchArgs
import me.magnum.melonds.ui.emulator.model.PauseMenu
import me.magnum.melonds.ui.emulator.model.RAEventUi
import me.magnum.melonds.ui.emulator.model.RAIntegrationEvent
import me.magnum.melonds.ui.emulator.model.RumbleEvent
import me.magnum.melonds.ui.emulator.model.RuntimeInputLayoutConfiguration
import me.magnum.melonds.ui.emulator.model.RuntimeRendererConfiguration
import me.magnum.melonds.ui.emulator.model.ToastEvent
import me.magnum.melonds.ui.emulator.rewind.model.RewindSaveState
import me.magnum.melonds.ui.emulator.rom.RomPauseMenuOption
import me.magnum.melonds.ui.emulator.savestate.SaveStateOperationCoordinator
import me.magnum.melonds.ui.emulator.savestate.recoverStorageFailure
import me.magnum.melonds.utils.EventSharedFlow
import java.util.UUID
import javax.inject.Inject
import kotlin.coroutines.CoroutineContext
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.math.roundToInt
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class EmulatorViewModel @Inject constructor(
    private val settingsRepository: SettingsRepository,
    private val romsRepository: RomsRepository,
    private val cheatsRepository: CheatsRepository,
    private val retroAchievementsRepository: RetroAchievementsRepository,
    private val romFileProcessorFactory: RomFileProcessorFactory,
    private val layoutsRepository: LayoutsRepository,
    private val backgroundsRepository: BackgroundRepository,
    private val saveStatesRepository: SaveStatesRepository,
    private val screenshotFrameBufferProvider: ScreenshotFrameBufferProvider,
    private val uiLayoutProvider: UILayoutProvider,
    private val emulatorManager: EmulatorManager,
    private val emulatorSession: EmulatorSession,
    private val retroAchievementsSubmissionHandler: RetroAchievementsSubmissionHandler,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val sessionCoroutineScope = EmulatorSessionCoroutineScope()
    private var raSessionJob: Job? = null
    private val saveStateOperations = SaveStateOperationCoordinator()
    private var isStopping = false
    private var isActivityResumed = false
    private var twoPlayerOperationRunning = false
    private val _selectedPlayer = MutableStateFlow<Int?>(null)
    val selectedPlayer = _selectedPlayer.asStateFlow()
    private val _twoPlayerResult = MutableStateFlow<EmulatorUiEvent?>(null)
    val twoPlayerResult = _twoPlayerResult.asStateFlow()
    fun consumeTwoPlayerResult() { _twoPlayerResult.value = null }
    fun isTwoPlayerOperationRunning(): Boolean = twoPlayerOperationRunning

    fun isTwoPlayerActive(): Boolean = _selectedPlayer.value != null

    private fun blockUnsupportedTwoPlayerOperation(): Boolean {
        if (!isTwoPlayerActive() && !twoPlayerOperationRunning) return false
        _toastEvent.tryEmit(ToastEvent.UnavailableInTwoPlayer)
        return true
    }

    private val _emulatorState = MutableStateFlow<EmulatorState>(EmulatorState.Uninitialized)
    val emulatorState = _emulatorState.asStateFlow()

    private val _layout = MutableStateFlow<LayoutConfiguration?>(null)

    private val _currentLayout = uiLayoutProvider.currentLayout.shareIn(viewModelScope, SharingStarted.Lazily)

    private val _runtimeLayout = MutableStateFlow<RuntimeInputLayoutConfiguration?>(null)
    val runtimeLayout = _runtimeLayout.asStateFlow()

    val controllerConfiguration = settingsRepository.observeControllerConfiguration()

    private val _runtimeRendererConfiguration = MutableStateFlow<RuntimeRendererConfiguration?>(null)
    val runtimeRendererConfiguration = _runtimeRendererConfiguration.asStateFlow()

    private val _mainScreenBackground = MutableStateFlow(RuntimeBackground.None)
    val mainScreenBackground = _mainScreenBackground.asStateFlow()

    private val _secondaryScreenBackground = MutableStateFlow(RuntimeBackground.None)
    val secondaryScreenBackground = _secondaryScreenBackground.asStateFlow()

    private val _rumbleEvent = MutableSharedFlow<RumbleEvent>(extraBufferCapacity = 100, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    val rumbleEvent = _rumbleEvent.asSharedFlow()

    private val _achievementsEvent = MutableSharedFlow<RAEventUi>(extraBufferCapacity = 100, onBufferOverflow = BufferOverflow.SUSPEND)
    val achievementsEvent = _achievementsEvent.asSharedFlow()

    private val _currentFps = MutableStateFlow<Int?>(null)
    val currentFps = _currentFps.asStateFlow()

    private val _toastEvent = EventSharedFlow<ToastEvent>()
    val toastEvent = _toastEvent.asSharedFlow()

    private val _raIntegrationEvent = EventSharedFlow<RAIntegrationEvent>()
    val integrationEvent = _raIntegrationEvent.asSharedFlow()

    val pendingSubmissionsSummary = retroAchievementsSubmissionHandler.getPendingSubmissionsSummaryFlow()

    private val _uiEvent = EventSharedFlow<EmulatorUiEvent>()
    val uiEvent = _uiEvent.asSharedFlow()

    init {
        viewModelScope.launch {
            _layout.filterNotNull().collect {
                uiLayoutProvider.setCurrentLayoutConfiguration(it)
            }
        }

        val launchArgs = LaunchArgs.fromSavedStateHandle(savedStateHandle)
        if (launchArgs != null) {
            launchEmulator(launchArgs)
        } else {
            _uiEvent.tryEmit(EmulatorUiEvent.CloseEmulator)
        }
    }

    fun relaunchWithNewArgs(args: LaunchArgs) {
        if (isStopping) return
        isStopping = true
        saveStateOperations.requestPause()
        viewModelScope.launch {
            if (_emulatorState.value.isRunning()) {
                stopEmulator()
            }
            isStopping = false
            launchEmulator(args)
        }
    }

    fun onRomLaunchValidated(rom: Rom) {
        viewModelScope.launch {
            launchRom(rom)
        }
    }

    fun onFirmwareLaunchValidated(consoleType: ConsoleType) {
        viewModelScope.launch {
            launchFirmware(consoleType)
        }
    }

    private fun launchEmulator(args: LaunchArgs) {
        when (args) {
            is LaunchArgs.RomObject -> loadRom(args.rom)
            is LaunchArgs.RomUri -> loadRom(args.uri)
            is LaunchArgs.RomPath -> loadRom(args.path)
            is LaunchArgs.Firmware -> _emulatorState.value = EmulatorState.ValidatingFirmware(args.consoleType)
        }
    }

    private fun loadRom(rom: Rom) {
        viewModelScope.launch {
            resetEmulatorState(EmulatorState.LoadingRom)
            sessionCoroutineScope.launch {
                _emulatorState.value = EmulatorState.ValidatingRom(rom)
            }
        }
    }

    private fun loadRom(romUri: Uri) {
        viewModelScope.launch {
            resetEmulatorState(EmulatorState.LoadingRom)
            sessionCoroutineScope.launch {
                val rom = romsRepository.getRomAtUri(romUri)
                if (rom != null) {
                    _emulatorState.value = EmulatorState.ValidatingRom(rom)
                } else {
                    _emulatorState.value = EmulatorState.RomNotFoundError(romUri.toString())
                }
            }
        }
    }

    private fun loadRom(romPath: String) {
        viewModelScope.launch {
            resetEmulatorState(EmulatorState.LoadingRom)
            sessionCoroutineScope.launch {
                val rom = romsRepository.getRomAtPath(romPath)
                if (rom != null) {
                    _emulatorState.value = EmulatorState.ValidatingRom(rom)
                } else {
                    _emulatorState.value = EmulatorState.RomNotFoundError(romPath)
                }
            }
        }
    }

    private suspend fun launchRom(rom: Rom) = coroutineScope {
        startEmulatorSession(EmulatorSession.SessionType.RomSession(rom))
        startObservingMainScreenBackground()
        startObservingSecondaryScreenBackground()
        startObservingRuntimeInputLayoutConfiguration()
        startObservingRendererConfiguration()
        startObservingEmulatorEvents()
        startObservingAchievementEvents()
        startObservingLayoutForRom(rom)
        startRetroAchievementsSession(rom)

        val cheats = getRomInfo(rom)?.let { getRomEnabledCheats(it) } ?: emptyList()
        val result = emulatorManager.loadRom(rom, cheats)
        when (result) {
            is RomLaunchResult.LaunchFailedRomNotFound,
            is RomLaunchResult.LaunchFailedRomNotSupported,
            is RomLaunchResult.LaunchFailedSramProblem,
            is RomLaunchResult.LaunchFailed -> {
                _emulatorState.value = EmulatorState.RomLoadError
            }
            is RomLaunchResult.LaunchSuccessful -> {
                if (!result.isGbaLoadSuccessful) {
                    _toastEvent.tryEmit(ToastEvent.GbaLoadFailed)
                }
                _emulatorState.value = EmulatorState.RunningRom(rom)
                updatePausePolicyAfterLaunch()
                startTrackingFps()
                startTrackingPlayTime(rom)
            }
        }
    }

    private fun launchFirmware(consoleType: ConsoleType) {
        viewModelScope.launch {
            resetEmulatorState(EmulatorState.LoadingFirmware)
            startEmulatorSession(EmulatorSession.SessionType.FirmwareSession(consoleType))
            sessionCoroutineScope.launch {
                startObservingMainScreenBackground()
                startObservingSecondaryScreenBackground()
                startObservingRuntimeInputLayoutConfiguration()
                startObservingRendererConfiguration()
                startObservingLayoutForFirmware()
                startObservingEmulatorEvents()

                val result = emulatorManager.loadFirmware(consoleType)
                when (result) {
                    is FirmwareLaunchResult.LaunchFailed -> {
                        _emulatorState.value = EmulatorState.FirmwareLoadError(result.reason)
                    }
                    FirmwareLaunchResult.LaunchSuccessful -> {
                        _emulatorState.value = EmulatorState.RunningFirmware(consoleType)
                        updatePausePolicyAfterLaunch()
                        startTrackingFps()
                    }
                }
            }
        }
    }

    fun setSystemOrientation(orientation: Orientation) {
        uiLayoutProvider.updateCurrentOrientation(orientation)
    }

    fun setUiSize(width: Int, height: Int) {
        uiLayoutProvider.updateUiSize(width, height)
    }

    fun setUiInsets(insets: Insets) {
        uiLayoutProvider.updateUiInsets(insets)
    }

    fun setScreenFolds(folds: List<ScreenFold>) {
        uiLayoutProvider.updateFolds(folds)
    }

    fun setConnectedDisplays(displays: LayoutDisplayPair) {
        uiLayoutProvider.updateDisplays(displays)
    }

    fun onSettingsChanged() {
        if (isTwoPlayerActive()) return
        val currentState = _emulatorState.value
        sessionCoroutineScope.launch {
            val sessionUpdateActions = emulatorSession.updateRetroAchievementsSettings(
                retroAchievementsRepository.isUserAuthenticated(),
                settingsRepository.isRetroAchievementsHardcoreEnabled(),
            )

            when (currentState) {
                is EmulatorState.RunningRom -> emulatorManager.updateRomEmulatorConfiguration(currentState.rom)
                is EmulatorState.RunningFirmware -> emulatorManager.updateFirmwareEmulatorConfiguration(currentState.console)
                else -> {
                    // Do nothing
                }
            }

            dispatchSessionUpdateActions(sessionUpdateActions)
        }
    }

    fun onCheatsChanged() {
        if (isTwoPlayerActive()) return
        val rom = (_emulatorState.value as? EmulatorState.RunningRom)?.rom ?: return

        getRomInfo(rom)?.let {
            sessionCoroutineScope.launch {
                val cheats = getRomEnabledCheats(it)
                emulatorManager.updateCheats(cheats)
            }
        }
    }

    // Main-thread input must stop before asynchronous native teardown begins.
    fun canAcceptInput(): Boolean = !isStopping && !twoPlayerOperationRunning && _emulatorState.value.isRunning()

    fun onActivityResumed(allowResume: Boolean) {
        isActivityResumed = true
        if (allowResume) resumeEmulator()
    }

    fun onActivityPaused() {
        isActivityResumed = false
        pauseEmulator(false)
    }

    private suspend fun updatePausePolicyAfterLaunch() {
        if (isActivityResumed && !isStopping) {
            saveStateOperations.requestResume()
        } else {
            saveStateOperations.requestPause()
            emulatorManager.pauseEmulator()
        }
    }

    fun pauseEmulator(showPauseMenu: Boolean) {
        // Record the pause before suspending: a pending save must not undo this request.
        saveStateOperations.requestPause()
        sessionCoroutineScope.launch {
            emulatorManager.pauseEmulator()
            if (showPauseMenu) {
                val pauseOptions = when (_emulatorState.value) {
                    is EmulatorState.RunningRom -> {
                        RomPauseMenuOption.entries.filter {
                            filterRomPauseMenuOption(it)
                        }
                    }
                    is EmulatorState.RunningFirmware -> {
                        FirmwarePauseMenuOption.entries
                    }
                    else -> null
                }

                if (pauseOptions != null) {
                    _uiEvent.emit(EmulatorUiEvent.ShowPauseMenu(PauseMenu(pauseOptions)))
                }
            }
        }
    }

    fun resumeEmulator() {
        if (isStopping || !isActivityResumed || twoPlayerOperationRunning) return
        saveStateOperations.requestResume()
        if (!saveStateOperations.isRunning) {
            sessionCoroutineScope.launch {
                emulatorManager.resumeEmulator()
            }
        }
    }

    fun resetEmulator() {
        if (blockUnsupportedTwoPlayerOperation()) return
        if (_emulatorState.value.isRunning() && isActivityResumed && !saveStateOperations.isRunning && !isStopping) {
            saveStateOperations.requestResume()
            sessionCoroutineScope.launch {
                emulatorManager.resetEmulator()
                _achievementsEvent.emit(RAEventUi.Reset)
            }
        }
    }

    fun exitEmulator(force: Boolean = false) {
        if (!force && retroAchievementsSubmissionHandler.hasPendingSubmissions()) {
            _uiEvent.tryEmit(EmulatorUiEvent.ShowPendingSubmissionsDialog)
            retroAchievementsSubmissionHandler.retrySubmissionsImmediately()
        } else {
            stopEmulatorAndExit()
        }
    }

    private suspend fun stopEmulator() {
        saveStateOperations.requestPause()
        sessionCoroutineScope.cancel()
        _achievementsEvent.tryEmit(RAEventUi.Reset)
        emulatorManager.stopEmulator()
        screenshotFrameBufferProvider.clearBuffer()
    }

    private fun stopEmulatorAndExit() {
        if (isStopping) return
        isStopping = true
        saveStateOperations.requestPause()
        viewModelScope.launch {
            stopEmulator()
            _uiEvent.emit(EmulatorUiEvent.CloseEmulator)
        }
    }

    private fun startTrackingPlayTime(rom: Rom) {
        sessionCoroutineScope.launch {
            var lastTime = System.currentTimeMillis()
            while (isActive) {
                delay(1000)
                val now = System.currentTimeMillis()
                romsRepository.addRomPlayTime(rom, (now - lastTime).milliseconds)
                lastTime = now
            }
        }
    }

    fun onPauseMenuOptionSelected(option: PauseMenuOption) {
        when (option) {
            is RomPauseMenuOption -> {
                if (!filterRomPauseMenuOption(option) || twoPlayerOperationRunning) return
                when (option) {
                    RomPauseMenuOption.TWO_PLAYER -> sessionCoroutineScope.launch {
                        val rom = (_emulatorState.value as? EmulatorState.RunningRom)?.rom ?: return@launch
                        _uiEvent.emit(EmulatorUiEvent.ShowTwoPlayerMenu(emulatorManager.getTwoPlayerSaveInfo(rom)))
                    }
                    RomPauseMenuOption.SWITCH_PLAYER -> switchPlayer()
                    RomPauseMenuOption.SETTINGS -> _uiEvent.tryEmit(EmulatorUiEvent.OpenScreen.SettingsScreen)
                    RomPauseMenuOption.SAVE_STATE -> {
                        (_emulatorState.value as? EmulatorState.RunningRom)?.let {
                            val saveStateSlots = getRomSaveStateSlots(it.rom)
                            _uiEvent.tryEmit(EmulatorUiEvent.ShowRomSaveStates(saveStateSlots, EmulatorUiEvent.ShowRomSaveStates.Reason.SAVING))
                        }
                    }
                    RomPauseMenuOption.LOAD_STATE -> {
                        (_emulatorState.value as? EmulatorState.RunningRom)?.let {
                            val saveStateSlots = getRomSaveStateSlots(it.rom)
                            _uiEvent.tryEmit(EmulatorUiEvent.ShowRomSaveStates(saveStateSlots, EmulatorUiEvent.ShowRomSaveStates.Reason.LOADING))
                        }
                    }
                    RomPauseMenuOption.REWIND -> {
                        sessionCoroutineScope.launch {
                            val rewindWindow = emulatorManager.getRewindWindow()
                            _uiEvent.emit(EmulatorUiEvent.ShowRewindWindow(rewindWindow))
                        }
                    }
                    RomPauseMenuOption.CHEATS -> {
                        (_emulatorState.value as? EmulatorState.RunningRom)?.let {
                            getRomInfo(it.rom)?.let { romInfo ->
                                _uiEvent.tryEmit(EmulatorUiEvent.OpenScreen.CheatsScreen(romInfo))
                            }
                        }
                    }
                    RomPauseMenuOption.VIEW_ACHIEVEMENTS -> _uiEvent.tryEmit(EmulatorUiEvent.ShowAchievementList)
                    RomPauseMenuOption.RESET -> resetEmulator()
                    RomPauseMenuOption.EXIT -> exitEmulator(force = false)
                }
            }
            is FirmwarePauseMenuOption -> {
                when (option) {
                    FirmwarePauseMenuOption.SETTINGS -> _uiEvent.tryEmit(EmulatorUiEvent.OpenScreen.SettingsScreen)
                    FirmwarePauseMenuOption.RESET -> resetEmulator()
                    FirmwarePauseMenuOption.EXIT -> stopEmulatorAndExit()
                }
            }
        }
    }

    fun onOpenRewind() {
        if (blockUnsupportedTwoPlayerOperation()) return
        if (saveStateOperations.isRunning || isStopping) return
        if (!settingsRepository.isRewindEnabled()) {
            _toastEvent.tryEmit(ToastEvent.RewindNotEnabled)
            return
        }

        if (!emulatorSession.areSaveStateLoadsAllowed()) {
            _toastEvent.tryEmit(ToastEvent.RewindNotAvailableWhileRAHardcoreModeEnabled)
            return
        }

        sessionCoroutineScope.launch {
            emulatorManager.pauseEmulator()
            val rewindWindow = emulatorManager.getRewindWindow()
            _uiEvent.emit(EmulatorUiEvent.ShowRewindWindow(rewindWindow))
        }
    }

    fun rewindToState(rewindSaveState: RewindSaveState) {
        if (blockUnsupportedTwoPlayerOperation()) return
        sessionCoroutineScope.launch {
            emulatorManager.loadRewindState(rewindSaveState)
        }
    }

    fun saveStateToSlot(slot: SaveStateSlot) {
        if (blockUnsupportedTwoPlayerOperation()) return
        val currentState = _emulatorState.value as? EmulatorState.RunningRom ?: return
        if (isStopping || !isActivityResumed || saveStateOperations.isRunning) return
        // Picking a slot dismisses the pause UI, unless a later lifecycle event pauses again.
        saveStateOperations.requestResume()
        runStateOperation(
            operation = { saveRomState(currentState.rom, slot) },
            onResult = { if (!it) _toastEvent.emit(ToastEvent.StateSaveFailed) },
        )
    }

    fun loadStateFromSlot(slot: SaveStateSlot) {
        if (blockUnsupportedTwoPlayerOperation()) return
        val currentState = _emulatorState.value as? EmulatorState.RunningRom ?: return
        if (isStopping || !isActivityResumed || saveStateOperations.isRunning) return
        if (!slot.exists) {
            _toastEvent.tryEmit(ToastEvent.StateStateDoesNotExist)
            resumeEmulator()
            return
        }
        saveStateOperations.requestResume()
        runStateOperation(
            operation = { loadRomState(currentState.rom, slot) },
            onResult = { if (!it) _toastEvent.emit(ToastEvent.StateLoadFailed) },
        )
    }

    fun doQuickSave() {
        if (blockUnsupportedTwoPlayerOperation()) return
        if (isStopping || !isActivityResumed) return
        when (val currentState = _emulatorState.value) {
            is EmulatorState.RunningRom -> runStateOperation(
                operation = {
                    val quickSlot = withContext(Dispatchers.IO) {
                        saveStatesRepository.getRomQuickSaveStateSlot(currentState.rom)
                    }
                    saveRomState(currentState.rom, quickSlot)
                },
                onResult = {
                    _toastEvent.emit(if (it) ToastEvent.QuickSaveSuccessful else ToastEvent.StateSaveFailed)
                },
            )
            is EmulatorState.RunningFirmware -> _toastEvent.tryEmit(ToastEvent.CannotSaveStateWhenRunningFirmware)
            else -> Unit
        }
    }

    fun doQuickLoad() {
        if (blockUnsupportedTwoPlayerOperation()) return
        if (isStopping || !isActivityResumed) return
        when (val currentState = _emulatorState.value) {
            is EmulatorState.RunningRom -> {
                if (emulatorSession.areSaveStateLoadsAllowed()) {
                    runStateOperation(
                        operation = {
                            val quickSlot = withContext(Dispatchers.IO) {
                                saveStatesRepository.getRomQuickSaveStateSlot(currentState.rom)
                            }
                            loadRomState(currentState.rom, quickSlot)
                        },
                        onResult = {
                            _toastEvent.emit(if (it) ToastEvent.QuickLoadSuccessful else ToastEvent.StateLoadFailed)
                        },
                    )
                } else {
                    _toastEvent.tryEmit(ToastEvent.CannotUseSaveStatesWhenRAHardcoreIsEnabled)
                }
            }
            is EmulatorState.RunningFirmware -> _toastEvent.tryEmit(ToastEvent.CannotLoadStateWhenRunningFirmware)
            else -> Unit
        }
    }

    private fun runStateOperation(operation: suspend () -> Boolean, onResult: suspend (Boolean) -> Unit) {
        sessionCoroutineScope.launch {
            saveStateOperations.run(
                pause = { emulatorManager.pauseEmulator() },
                operation = operation,
                onResult = onResult,
                resume = {
                    if (isActivityResumed && !isStopping) emulatorManager.resumeEmulator()
                },
            )
        }
    }

    fun deleteSaveStateSlot(slot: SaveStateSlot): List<SaveStateSlot>? {
        return (_emulatorState.value as? EmulatorState.RunningRom)?.let {
            saveStatesRepository.deleteRomSaveState(it.rom, slot)
            getRomSaveStateSlots(it.rom)
        }
    }

    private suspend fun saveRomState(rom: Rom, slot: SaveStateSlot): Boolean {
        val slotUri = withContext(Dispatchers.IO) { saveStatesRepository.getRomSaveStateUri(rom, slot) }
        if (!emulatorManager.saveState(slotUri)) {
            return false
        }

        // Alpha safety: automatic thumbnails are deliberately omitted. The pinned core's
        // capture waits unconditionally for a future frame and can race teardown/lost wakeups.
        // Preserve the real save and remove an old preview rather than showing misleading art.
        // A cosmetic cleanup failure must never turn a successful state save into a failure.
        recoverStorageFailure {
            withContext(Dispatchers.IO) {
                saveStatesRepository.deleteRomSaveStateScreenshot(rom, slot)
            }
            true
        }

        return true
    }

    private suspend fun loadRomState(rom: Rom, slot: SaveStateSlot): Boolean {
        if (!slot.exists) {
            return false
        }

        val slotUri = withContext(Dispatchers.IO) { saveStatesRepository.getRomSaveStateUri(rom, slot) }
        val success = emulatorManager.loadState(slotUri)
        if (success) {
            _achievementsEvent.emit(RAEventUi.Reset)
        }

        return success
    }

    private fun startObservingRuntimeInputLayoutConfiguration() {
        sessionCoroutineScope.launch {
            combine(
                _layout,
                _currentLayout,
                settingsRepository.getSoftInputBehaviour(),
                settingsRepository.isTouchHapticFeedbackEnabled(),
                settingsRepository.getSoftInputOpacity(),
            ) { layoutConfiguration, variant, softInputBehaviour, isHapticFeedbackEnabled, inputOpacity ->
                val layout = variant?.second
                if (layoutConfiguration == null || layout == null) {
                    null
                } else {
                    val opacity = if (layoutConfiguration.useCustomOpacity) {
                        layoutConfiguration.opacity
                    } else {
                        inputOpacity
                    }

                    RuntimeInputLayoutConfiguration(
                        softInputBehaviour = softInputBehaviour,
                        softInputOpacity = opacity,
                        isHapticFeedbackEnabled = isHapticFeedbackEnabled,
                        layoutOrientation = layoutConfiguration.orientation,
                        layout = layout,
                    )
                }
            }.collect(_runtimeLayout)
        }
    }

    private fun resetEmulatorState(newState: EmulatorState) {
        sessionCoroutineScope.notifyNewSessionStarted()
        emulatorSession.reset()
        raSessionJob = null
        _selectedPlayer.value = null
        _twoPlayerResult.value = null
        twoPlayerOperationRunning = false
        _currentFps.value = null
        _emulatorState.value = newState
        _mainScreenBackground.value = RuntimeBackground.None
        _secondaryScreenBackground.value = RuntimeBackground.None
        _layout.value = null
    }

    private fun startObservingEmulatorEvents() {
        sessionCoroutineScope.launch {
            emulatorManager.emulatorEvents.collect {
                when (it) {
                    is EmulatorEvent.RumbleStart -> _rumbleEvent.tryEmit(RumbleEvent.RumbleStart(it.duration))
                    EmulatorEvent.RumbleStop -> _rumbleEvent.tryEmit(RumbleEvent.RumbleStop)
                    is EmulatorEvent.Stop -> {
                        when (it.reason) {
                            EmulatorEvent.Stop.Reason.GBAModeNotSupported -> _toastEvent.tryEmit(ToastEvent.GbaModeNotSupported)
                            EmulatorEvent.Stop.Reason.InternalError,
                            EmulatorEvent.Stop.Reason.BadExceptionRegion -> _toastEvent.tryEmit(ToastEvent.InternalError)
                            EmulatorEvent.Stop.Reason.PowerOff -> { /* no-op */ }
                        }
                        stopEmulatorAndExit()
                    }
                }
            }
        }
    }

    private fun startObservingAchievementEvents() {
        sessionCoroutineScope.launch {
            emulatorManager.observeRetroAchievementEvents().collect {
                when (it) {
                    is RAEvent.OnAchievementPrimed -> onAchievementPrimed(it.achievementId)
                    is RAEvent.OnAchievementUnPrimed -> onAchievementUnPrimed(it.achievementId)
                    is RAEvent.OnAchievementTriggered -> onAchievementTriggered(it.achievementId)
                    is RAEvent.OnAchievementProgressUpdated -> onAchievementProgressUpdated(it)
                    is RAEvent.OnLeaderboardAttemptStarted -> onLeaderboardAttemptStarted(it)
                    is RAEvent.OnLeaderboardAttemptUpdated -> onLeaderboardAttemptUpdated(it)
                    is RAEvent.OnLeaderboardAttemptCompleted -> onLeaderboardAttemptCompleted(it)
                    is RAEvent.OnLeaderboardAttemptCancelled -> onLeaderboardAttemptCancelled(it)
                }
            }
        }
    }

    private fun startObservingMainScreenBackground() {
        sessionCoroutineScope.launch {
            combine(_currentLayout, ensureEmulatorIsRunning()) { variant, _ ->
                val layout = variant?.second
                if (layout == null) {
                    RuntimeBackground.None
                } else {
                    loadBackground(layout.mainScreenLayout.backgroundId, layout.mainScreenLayout.backgroundMode)
                }
            }.collect(_mainScreenBackground)
        }
    }

    private fun startObservingSecondaryScreenBackground() {
        sessionCoroutineScope.launch {
            combine(_currentLayout, ensureEmulatorIsRunning()) { variant, _ ->
                val layout = variant?.second
                if (layout == null) {
                    RuntimeBackground.None
                } else {
                    loadBackground(layout.secondaryScreenLayout.backgroundId, layout.secondaryScreenLayout.backgroundMode)
                }
            }.collect(_secondaryScreenBackground)
        }
    }

    private fun startObservingLayoutForRom(rom: Rom) {
        val romLayoutId = rom.config.layoutId
        val layoutFlow = if (romLayoutId == null) {
            getGlobalLayoutFlow()
        } else {
            // Load and observe ROM layout but switch to global layout if the ROM layout stops existing
            layoutsRepository.observeLayout(romLayoutId)
                .onCompletion {
                    emitAll(getGlobalLayoutFlow())
                }
        }

        sessionCoroutineScope.launch {
            combine(layoutFlow, ensureEmulatorIsRunning()) { layout, _ ->
                layout
            }.collect(_layout)
        }
    }

    private fun startObservingRendererConfiguration() {
        sessionCoroutineScope.launch {
            settingsRepository.observeRenderConfiguration().collectLatest {
                _runtimeRendererConfiguration.value = RuntimeRendererConfiguration(it.videoFiltering, it.resolutionScaling)
            }
        }
    }

    private fun startObservingLayoutForFirmware() {
        _layout.value = null

        sessionCoroutineScope.launch {
            combine(getGlobalLayoutFlow(), ensureEmulatorIsRunning()) { layout, _ ->
                layout
            }.collect(_layout)
        }
    }

    private suspend fun loadBackground(backgroundId: UUID?, mode: BackgroundMode): RuntimeBackground {
        return if (backgroundId == null) {
            RuntimeBackground(null, mode)
        } else {
            val background = backgroundsRepository.getBackground(backgroundId)
            RuntimeBackground(background, mode)
        }
    }

    private fun getGlobalLayoutFlow(): Flow<LayoutConfiguration> {
        return settingsRepository.observeSelectedLayoutId()
            .flatMapLatest {
                layoutsRepository.observeLayout(it)
                    .onCompletion {
                        emitAll(layoutsRepository.observeLayout(LayoutConfiguration.DEFAULT_ID))
                    }
            }
    }

    private fun getRomInfo(rom: Rom): RomInfo? {
        val fileRomProcessor = romFileProcessorFactory.getFileRomProcessorForDocument(rom.uri)
        return fileRomProcessor?.getRomInfo(rom)
    }

    private fun getRomSaveStateSlots(rom: Rom): List<SaveStateSlot> {
        return saveStatesRepository.getRomSaveStates(rom)
    }

    fun isSustainedPerformanceModeEnabled(): Boolean {
        return settingsRepository.isSustainedPerformanceModeEnabled()
    }

    fun getFpsCounterPosition(): FpsCounterPosition {
        return settingsRepository.getFpsCounterPosition()
    }

    private suspend fun getRomEnabledCheats(romInfo: RomInfo): List<Cheat> {
        if (!settingsRepository.areCheatsEnabled() || !emulatorSession.areCheatsEnabled()) {
            return emptyList()
        }

        return cheatsRepository.getRomEnabledCheats(romInfo)
    }

    private suspend fun getRomAchievementData(rom: Rom): GameAchievementData {
        if (!retroAchievementsRepository.isUserAuthenticated()) {
            return GameAchievementData.withDisabledRetroAchievementsIntegration(GameAchievementData.IntegrationStatus.DISABLED_NOT_LOGGED_IN)
        }

        return retroAchievementsRepository.getUserGameData(rom.retroAchievementsHash, emulatorSession.isRetroAchievementsHardcoreModeEnabled).fold(
            onSuccess = { userGameData ->
                val gameSummary = retroAchievementsRepository.getGameSummary(rom.retroAchievementsHash)

                if (userGameData != null) {
                    val achievements = userGameData.sets.flatMap { it.achievements }
                    val leaderboards = userGameData.sets.flatMap { it.leaderboards }
                    val hasLeaderboards = leaderboards.isNotEmpty() && emulatorSession.areLeaderboardsEnabled()

                    if (achievements.isEmpty() && !hasLeaderboards) {
                        GameAchievementData.withLimitedRetroAchievementsIntegration(
                            richPresencePatch = gameSummary?.richPresencePatch,
                            icon = gameSummary?.icon,
                        )
                    } else {
                        val lockedAchievements = achievements.filter { !it.isUnlocked }.map { RASimpleAchievement(it.achievement.id, it.achievement.memoryAddress) }
                        val leaderboards = if (hasLeaderboards) {
                            leaderboards.map { RASimpleLeaderboard(it.id, it.mem, it.format) }
                        } else {
                            emptyList()
                        }

                        GameAchievementData.withFullRetroAchievementsIntegration(
                            lockedAchievements = lockedAchievements,
                            leaderboards = leaderboards,
                            totalAchievementCount = achievements.size,
                            richPresencePatch = gameSummary?.richPresencePatch,
                            icon = gameSummary?.icon,
                        )
                    }
                } else {
                    GameAchievementData.withDisabledRetroAchievementsIntegration(
                        status = GameAchievementData.IntegrationStatus.DISABLED_GAME_NOT_FOUND,
                        icon = gameSummary?.icon,
                    )
                }
            },
            onFailure = {
                // Maybe we have the game summary cached. Could allow the icon to be displayed, which looks better
                val gameSummary = retroAchievementsRepository.getGameSummary(rom.retroAchievementsHash)
                GameAchievementData.withDisabledRetroAchievementsIntegration(GameAchievementData.IntegrationStatus.DISABLED_LOAD_ERROR, gameSummary?.icon)
            }
        )
    }

    private fun onAchievementTriggered(achievementId: Long) {
        sessionCoroutineScope.launch {
            retroAchievementsRepository.getAchievement(achievementId).onSuccess { achievement ->
                if (achievement != null) {
                    val isHardcoreModeEnabled = emulatorSession.isRetroAchievementsHardcoreModeEnabled
                    retroAchievementsSubmissionHandler.addPendingAchievementSubmission(achievement, isHardcoreModeEnabled)
                }
            }
        }
    }

    private fun onAchievementPrimed(achievementId: Long) {
        if (settingsRepository.areRetroAchievementsActiveChallengeIndicatorsEnabled()) {
            sessionCoroutineScope.launch {
                retroAchievementsRepository.getAchievement(achievementId).onSuccess { achievement ->
                    if (achievement != null) {
                        _achievementsEvent.emit(RAEventUi.AchievementPrimed(achievement))
                    }
                }
            }
        }
    }

    private fun onAchievementUnPrimed(achievementId: Long) {
        sessionCoroutineScope.launch {
            retroAchievementsRepository.getAchievement(achievementId).onSuccess { achievement ->
                if (achievement != null) {
                    _achievementsEvent.emit(RAEventUi.AchievementUnPrimed(achievement))
                }
            }
        }
    }

    private fun onAchievementProgressUpdated(progressEvent: RAEvent.OnAchievementProgressUpdated) {
        if (settingsRepository.areRetroAchievementsProgressIndicatorsEnabled()) {
            sessionCoroutineScope.launch {
                retroAchievementsRepository.getAchievement(progressEvent.achievementId).onSuccess { achievement ->
                    if (achievement != null) {
                        _achievementsEvent.emit(RAEventUi.AchievementProgressUpdated(achievement, progressEvent.current, progressEvent.target, progressEvent.progress))
                    }
                }
            }
        }
    }

    private fun onLeaderboardAttemptStarted(startEvent: RAEvent.OnLeaderboardAttemptStarted) {
        sessionCoroutineScope.launch {
            if (settingsRepository.areRetroAchievementsLeaderboardIndicatorsEnabled()) {
                val leaderboard = retroAchievementsRepository.getLeaderboard(startEvent.leaderboardId)
                if (leaderboard != null) {
                    val setSummary = retroAchievementsRepository.getAchievementSetSummary(leaderboard.setId)
                    if (setSummary != null) {
                        _achievementsEvent.emit(RAEventUi.LeaderboardAttemptStarted(leaderboard, setSummary.iconUrl))
                    }
                }
            }
        }
    }

    private fun onLeaderboardAttemptUpdated(updateEvent: RAEvent.OnLeaderboardAttemptUpdated) {
        sessionCoroutineScope.launch {
            if (settingsRepository.areRetroAchievementsLeaderboardIndicatorsEnabled()) {
                _achievementsEvent.emit(RAEventUi.LeaderboardAttemptUpdated(updateEvent.leaderboardId, updateEvent.formattedValue))
            }
        }
    }

    private fun onLeaderboardAttemptCompleted(completionEvent: RAEvent.OnLeaderboardAttemptCompleted) {
        sessionCoroutineScope.launch {
            retroAchievementsRepository.getLeaderboard(completionEvent.leaderboardId)?.let { leaderboard ->
                retroAchievementsSubmissionHandler.addPendingLeaderboardSubmission(leaderboard, completionEvent.value, completionEvent.formattedValue)
            }
        }
    }

    private fun onLeaderboardAttemptCancelled(cancelEvent: RAEvent.OnLeaderboardAttemptCancelled) {
        sessionCoroutineScope.launch {
            _achievementsEvent.emit(RAEventUi.LeaderboardAttemptCancelled(cancelEvent.leaderboardId))
        }
    }

    private fun startRetroAchievementsSession(rom: Rom) {
        if (isTwoPlayerActive()) return
        raSessionJob = sessionCoroutineScope.launch {
            val achievementData = getRomAchievementData(rom)
            emulatorSession.updateRetroAchievementsIntegrationStatus(achievementData.retroAchievementsIntegrationStatus)
            if (!achievementData.isRetroAchievementsIntegrationEnabled) {
                if (achievementData.retroAchievementsIntegrationStatus == GameAchievementData.IntegrationStatus.DISABLED_LOAD_ERROR) {
                    _raIntegrationEvent.tryEmit(RAIntegrationEvent.Failed(achievementData.icon))
                }

                return@launch
            }

            launch {
                // Wait until the emulator has actually started
                ensureEmulatorIsRunning().firstOrNull()

                val isHardcoreModeEnabled = emulatorSession.isRetroAchievementsHardcoreModeEnabled
                val startResult = retroAchievementsRepository.startSession(rom.retroAchievementsHash, isHardcoreModeEnabled)
                if (startResult.isFailure) {
                    _raIntegrationEvent.tryEmit(RAIntegrationEvent.Failed(achievementData.icon))
                } else {
                    launch {
                        retroAchievementsSubmissionHandler.startEmulatorSession().collect(_achievementsEvent)
                    }

                    emulatorManager.setupRetroAchievements(achievementData)
                    if (achievementData.hasAchievements) {
                        _raIntegrationEvent.tryEmit(
                            RAIntegrationEvent.Loaded(
                                icon = achievementData.icon,
                                unlockedAchievements = achievementData.unlockedAchievementCount,
                                totalAchievements = achievementData.totalAchievementCount,
                            )
                        )
                    } else {
                        _raIntegrationEvent.tryEmit(RAIntegrationEvent.LoadedNoAchievements(achievementData.icon))
                    }

                    delay(30.seconds)
                    while (isActive) {
                        // TODO: Should we pause the session if the app goes to background? If so, how?
                        val richPresenceDescription = withContext(Dispatchers.IO) { MelonEmulator.getRichPresenceStatus() }
                        retroAchievementsRepository.sendSessionHeartbeat(rom.retroAchievementsHash, isHardcoreModeEnabled, richPresenceDescription)
                        delay(2.minutes)
                    }
                }
            }
        }
    }

    private fun startTrackingFps() {
        sessionCoroutineScope.launch {
            while (isActive) {
                delay(1.seconds)
                _currentFps.value = emulatorManager.getFps().roundToInt()
            }
        }
    }

    private fun filterRomPauseMenuOption(option: RomPauseMenuOption): Boolean {
        if (isTwoPlayerActive()) return option in setOf(RomPauseMenuOption.TWO_PLAYER, RomPauseMenuOption.SWITCH_PLAYER, RomPauseMenuOption.EXIT)
        return when (option) {
            RomPauseMenuOption.SWITCH_PLAYER -> false
            RomPauseMenuOption.REWIND -> settingsRepository.isRewindEnabled() && emulatorSession.areSaveStateLoadsAllowed()
            RomPauseMenuOption.LOAD_STATE -> emulatorSession.areSaveStateLoadsAllowed()
            RomPauseMenuOption.CHEATS -> emulatorSession.areCheatsEnabled()
            RomPauseMenuOption.VIEW_ACHIEVEMENTS -> emulatorSession.areRetroAchievementsEnabled()
            else -> true
        }
    }

    fun startSecondPlayer(importedSave: Uri? = null, createNew: Boolean = false) {
        val rom = (_emulatorState.value as? EmulatorState.RunningRom)?.rom
        if (rom == null || isStopping || twoPlayerOperationRunning || saveStateOperations.isRunning || isTwoPlayerActive()) {
            _twoPlayerResult.value = EmulatorUiEvent.TwoPlayerStarted(TwoPlayerStartResult.INVALID_SESSION)
            return
        }
        twoPlayerOperationRunning = true
        saveStateOperations.requestPause()
        sessionCoroutineScope.launch {
            try {
                emulatorManager.pauseEmulator()
                val result = emulatorManager.startSecondPlayer(rom, importedSave, createNew)
                if (result == TwoPlayerStartResult.SUCCESS) {
                    _selectedPlayer.value = MelonEmulator.getSelectedPlayer()
                    raSessionJob?.cancel()
                    raSessionJob = null
                    emulatorManager.unloadRetroAchievementsData()
                    _achievementsEvent.emit(RAEventUi.Reset)
                }
                twoPlayerOperationRunning = false
                _twoPlayerResult.value = EmulatorUiEvent.TwoPlayerStarted(result)
            } finally {
                twoPlayerOperationRunning = false
            }
        }
    }

    private fun switchPlayer() {
        val currentPlayer = _selectedPlayer.value ?: return
        if (isStopping || twoPlayerOperationRunning || saveStateOperations.isRunning) return
        twoPlayerOperationRunning = true
        sessionCoroutineScope.launch {
            try {
                if (emulatorManager.selectPlayer(1 - currentPlayer)) {
                    _selectedPlayer.value = 1 - currentPlayer
                } else {
                    _toastEvent.emit(ToastEvent.TwoPlayerSwitchFailed)
                }
            } finally {
                twoPlayerOperationRunning = false
            }
            resumeEmulator()
        }
    }

    fun exportTwoPlayerSave(destination: Uri, primaryBackup: Boolean) {
        val rom = (_emulatorState.value as? EmulatorState.RunningRom)?.rom
        if (rom == null || isStopping || twoPlayerOperationRunning || saveStateOperations.isRunning) {
            _twoPlayerResult.value = EmulatorUiEvent.TwoPlayerExported(false)
            return
        }
        twoPlayerOperationRunning = true
        saveStateOperations.requestPause()
        sessionCoroutineScope.launch {
            try {
                val success = emulatorManager.exportTwoPlayerSave(rom, destination, primaryBackup)
                twoPlayerOperationRunning = false
                _twoPlayerResult.value = EmulatorUiEvent.TwoPlayerExported(success)
            } finally {
                twoPlayerOperationRunning = false
            }
        }
    }

    private fun ensureEmulatorIsRunning(): Flow<Unit> {
        return _emulatorState.filter { it.isRunning() }.take(1).map { }
    }

    private suspend fun startEmulatorSession(sessionType: EmulatorSession.SessionType) {
        val isUserAuthenticatedInRetroAchievements = retroAchievementsRepository.isUserAuthenticated()
        val isRetroAchievementsHardcoreModeEnabled = settingsRepository.isRetroAchievementsHardcoreEnabled()
        emulatorSession.startSession(
            areRetroAchievementsEnabled = isUserAuthenticatedInRetroAchievements,
            isRetroAchievementsHardcoreModeEnabled = isRetroAchievementsHardcoreModeEnabled,
            sessionType = sessionType,
        )
    }

    private suspend fun dispatchSessionUpdateActions(actions: List<EmulatorSessionUpdateAction>) {
        actions.forEach {
            when (it) {
                EmulatorSessionUpdateAction.DisableRetroAchievements -> {
                    _achievementsEvent.tryEmit(RAEventUi.Reset)
                    emulatorManager.unloadRetroAchievementsData()
                    raSessionJob?.cancel()
                    raSessionJob = null
                }
                EmulatorSessionUpdateAction.EnableRetroAchievements -> {
                    (emulatorSession.currentSessionType() as? EmulatorSession.SessionType.RomSession)?.rom?.let { currentRom ->
                        startRetroAchievementsSession(currentRom)
                    }
                }
                EmulatorSessionUpdateAction.NotifyRetroAchievementsModeSwitch -> {
                    _toastEvent.tryEmit(ToastEvent.CannotSwitchRetroAchievementsMode)
                }
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        saveStateOperations.requestPause()
        sessionCoroutineScope.cancel()
        emulatorManager.cleanEmulator()
    }

    private class EmulatorSessionCoroutineScope : CoroutineScope {
        private var currentCoroutineContext: CoroutineContext = EmptyCoroutineContext

        override val coroutineContext: CoroutineContext get() = currentCoroutineContext

        fun notifyNewSessionStarted() {
            cancel()
            currentCoroutineContext = SupervisorJob() + Dispatchers.Main.immediate
        }

        fun cancel() {
            currentCoroutineContext.cancel()
        }
    }
}