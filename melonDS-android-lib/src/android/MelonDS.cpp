#include <cstring>
#include <utility>
#include <android/asset_manager.h>
#include <oboe/Oboe.h>
#include "EmulatorArgsBuilder.h"
#include "MelonDS.h"
#include "MelonDSAudio.h"
#include "OboeCallback.h"
#include "MicInputOboeCallback.h"
#include "OpenGLContext.h"
#include "mic_blow.h"
#include "NDS.h"
#include "GPU.h"
#include "GPU3D.h"
#include "GBACart.h"
#include "SPU.h"
#include "Platform.h"
#include "Savestate.h"
#include "MelonInstance.h"
#include "RewindManager.h"
#include "ROMManager.h"
#include "MPInterface.h"
#include "AndroidCameraHandler.h"
#include "renderer/ScreenshotRenderer.h"
#include "renderer/FrameQueue.h"
#include "retroachievements/RetroAchievementsManager.h"
#include "net/Net.h"
#include "net/Net_Slirp.h"
#include <fstream>
#include <atomic>
#include <algorithm>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <exception>

namespace MelonDSAndroid
{
    OpenGLContext *openGlContext;
    AndroidFileHandler* fileHandler;
    AndroidCameraHandler* cameraHandler;
    std::string internalFilesDir;
    std::shared_ptr<MelonEventMessenger> eventMessenger;
    std::shared_ptr<EmulatorConfiguration> currentConfiguration;
    std::shared_ptr<Net> net;

    std::shared_ptr<MelonInstance> instance;

    namespace {
        // Lifecycle changes are serialized by JNI's stateOperationMutex. This mutex
        // protects pointer snapshots taken concurrently by UI input/render/audio.
        std::mutex playerMutex;
        std::mutex peerControlMutex;
        std::mutex featureMutationMutex;
        std::shared_ptr<MelonInstance> secondInstance;
        std::atomic_bool twoPlayerActive{false};
        std::atomic_int selectedPlayer{0};
        std::string primaryRomPath;
        std::string primarySavePath;

        struct SecondPlayerSession {
            std::shared_ptr<MelonInstance> player;
            std::vector<u32> screenshot = std::vector<u32>(256 * 192 * 2);
            std::thread worker;
            std::mutex mutex;
            std::condition_variable condition;
            bool initialized = false;
            bool initializationSucceeded = false;
            bool pauseRequested = true;
            bool paused = true;
            bool stopping = false;
            bool finished = false;
            bool failed = false;
        };
        std::unique_ptr<SecondPlayerSession> secondSession;

        std::shared_ptr<MelonInstance> visibleInstance()
        {
            std::lock_guard lock(playerMutex);
            return selectedPlayer.load() == 1 && secondInstance ? secondInstance : instance;
        }

        void runSecondPlayer(SecondPlayerSession* session, long sharedContext)
        {
            OpenGLContext context;
            bool contextReady = false;
            bool playerStarted = false;
            bool initialized = false;
            bool runtimeFailed = false;
            try {
                contextReady = context.InitContext(sharedContext) && context.Use();
                if (contextReady) {
                    // Discard earlier GL errors, then verify the initial GL resources.
                    for (int i = 0; i < 16 && glGetError() != GL_NO_ERROR; ++i) {}
                    session->player->start();
                    playerStarted = true;
                    initialized = glGetError() == GL_NO_ERROR;
                }
                {
                    std::lock_guard lock(session->mutex);
                    session->initializationSucceeded = initialized;
                    session->initialized = true;
                    session->condition.notify_all();
                }

                if (initialized) {
                    std::unique_lock lock(session->mutex);
                    auto deadline = std::chrono::steady_clock::now();
                    while (!session->stopping) {
                        if (session->pauseRequested) {
                            session->paused = true;
                            session->condition.notify_all();
                            session->condition.wait(lock, [&] {
                                return session->stopping || !session->pauseRequested;
                            });
                            deadline = std::chrono::steady_clock::now();
                        }
                        if (session->stopping) break;
                        session->paused = false;
                        lock.unlock();
                        const u32 lines = session->player->runFrame();
                        lock.lock();
                        // The peer must execute concurrently with P1's RunFrame,
                        // because DS wireless reception blocks awaiting its replies.
                        const auto duration = std::chrono::nanoseconds(
                            std::max<int64_t>(1000000,
                                static_cast<int64_t>(1000000000.0 * lines / (60.0 * 263.0))));
                        deadline += duration;
                        const auto now = std::chrono::steady_clock::now();
                        if (deadline < now - duration) deadline = now;
                        session->condition.wait_until(lock, deadline, [&] {
                            return session->stopping || session->pauseRequested;
                        });
                    }
                }
            } catch (const std::exception& error) {
                Platform::Log(Platform::Error, "Second player stopped: %s\n", error.what());
                runtimeFailed = initialized;
            } catch (...) {
                Platform::Log(Platform::Error, "Second player stopped unexpectedly\n");
                runtimeFailed = initialized;
            }
            if (runtimeFailed) {
                // Keep textures/context alive until JNI's normal teardown excludes
                // presentation. Emitting an error must not race a P2 render callback.
                {
                    std::lock_guard lock(session->mutex);
                    session->paused = true;
                    session->pauseRequested = true;
                    session->failed = true;
                    session->condition.notify_all();
                }
                MPInterface::Get().End(1);
                if (eventMessenger) eventMessenger->onEmulatorStop(Platform::Unknown);
                std::unique_lock lock(session->mutex);
                session->condition.wait(lock, [&] { return session->stopping; });
            }
            MPInterface::Get().End(1);
            if (playerStarted) session->player->stop();
            if (contextReady) context.Release();
            context.DeInit();
            {
                std::lock_guard lock(session->mutex);
                session->initialized = true;
                session->finished = true;
                session->paused = true;
                session->condition.notify_all();
            }
        }

        void pauseSecondPlayer()
        {
            if (!secondSession) return;
            std::unique_lock lock(secondSession->mutex);
            secondSession->pauseRequested = true;
            secondSession->condition.notify_all();
            secondSession->condition.wait(lock, [&] {
                return secondSession->paused || secondSession->finished || secondSession->failed;
            });
        }

        void stopSecondPlayer()
        {
            std::lock_guard controlLock(peerControlMutex);
            if (!secondSession) return;
            {
                std::lock_guard lock(secondSession->mutex);
                secondSession->stopping = true;
                secondSession->condition.notify_all();
            }
            if (secondSession->worker.joinable()) secondSession->worker.join();
            {
                std::lock_guard lock(playerMutex);
                selectedPlayer.store(0);
                secondInstance.reset();
            }
            secondSession.reset();
            twoPlayerActive.store(false);
        }
    }

    bool isTwoPlayerActive() { return twoPlayerActive.load(); }
    int getSelectedPlayer() { return selectedPlayer.load(); }

    int startSecondPlayer(const std::string& romPath, const std::string& savePath)
    {
        std::lock_guard controlLock(peerControlMutex);
        std::lock_guard featureLock(featureMutationMutex);
        if (!instance || secondSession || romPath.empty() || savePath.empty() ||
            romPath != primaryRomPath || savePath == primarySavePath)
            return 1;
        if (!currentConfiguration || instance->getConsoleType() != 0 ||
            currentConfiguration->consoleType != 0 ||
            currentConfiguration->renderer != Renderer::Software)
            return 2;
        if (!openGlContext || openGlContext->GetContext() == EGL_NO_CONTEXT)
            return 4;

        std::unique_ptr<SecondPlayerSession> session;
        try {
            session = std::make_unique<SecondPlayerSession>();
            auto args = BuildArgsFromConfiguration(*currentConfiguration, 1);
            if (!args) return 3;
            // Local wireless is separate from Internet/WFC. Do not let a second
            // emulation thread call into the primary's global libslirp driver.
            auto peerNet = std::make_shared<Net>();
            session->player = std::make_shared<MelonInstance>(
                1, currentConfiguration, std::move(args.value()), peerNet,
                std::make_unique<ScreenshotRenderer>(session->screenshot.data()), 0);
            if (!session->player->loadRom(romPath, savePath)) return 3;
            session->player->disableRewind();
            // Switching the interface is safe only while both cores are paused.
            MPInterface::Set(MPInterface_Local);
            MPInterface::Get().Begin(0);
            session->worker = std::thread(runSecondPlayer, session.get(),
                                         reinterpret_cast<long>(openGlContext->GetContext()));
            {
                std::unique_lock lock(session->mutex);
                session->condition.wait(lock, [&] { return session->initialized; });
                if (!session->initializationSucceeded) {
                    session->stopping = true;
                    session->condition.notify_all();
                    lock.unlock();
                    session->worker.join();
                    MPInterface::Set(MPInterface_Dummy);
                    return 4;
                }
            }
        } catch (...) {
            if (session && session->worker.joinable()) {
                {
                    std::lock_guard lock(session->mutex);
                    session->stopping = true;
                    session->condition.notify_all();
                }
                session->worker.join();
            }
            MPInterface::Set(MPInterface_Dummy);
            return 4;
        }

        instance->loadCheats({});
        instance->unloadRetroAchievementsData();
        instance->disableRewind();
        instance->releaseAllInputs();
        session->player->releaseAllInputs();
        userDisableMic();
        {
            std::lock_guard lock(playerMutex);
            secondInstance = session->player;
            selectedPlayer.store(0);
        }
        secondSession = std::move(session);
        twoPlayerActive.store(true);
        return 0;
    }

    bool selectPlayer(int player)
    {
        std::lock_guard controlLock(peerControlMutex);
        if (player < 0 || player > 1 || (!isTwoPlayerActive() && player != 0))
            return false;
        pauseSecondPlayer();
        std::shared_ptr<MelonInstance> next;
        {
            std::lock_guard lock(playerMutex);
            if (!instance || (player == 1 && !secondInstance)) return false;
            instance->releaseAllInputs();
            if (secondInstance) secondInstance->releaseAllInputs();
            selectedPlayer.store(player);
            next = player == 1 ? secondInstance : instance;
        }
        setAudioActiveInstance(next);
        return true;
    }

    bool flushSaveFiles()
    {
        std::lock_guard controlLock(peerControlMutex);
        pauseSecondPlayer();
        if (!instance) return false;
        bool success = instance->flushSaveFiles();
        if (secondSession)
            success = secondSession->player->flushSaveFiles() && success;
        return success;
    }

    bool setupOpenGlContext();
    void cleanupOpenGlContext();

    /**
     * Used to set the emulator's initial configuration, before boot. To update the configuration during runtime, use @updateEmulatorConfiguration.
     *
     * @param emulatorConfiguration The emulator configuration during the next emulator run
     */
    void setConfiguration(EmulatorConfiguration emulatorConfiguration) {
        currentConfiguration = std::make_shared<EmulatorConfiguration>(std::move(emulatorConfiguration));
        internalFilesDir = currentConfiguration->internalFilesDir;

        net = std::make_shared<Net>();
        net->SetDriver(std::make_unique<Net_Slirp>([](const u8* data, int len) {
            net->RXEnqueue(data, len);
        }));
    }

    void setup(AndroidCameraHandler* androidCameraHandler, std::shared_ptr<MelonEventMessenger> androidEventMessenger, u32* screenshotBufferPointer, int instanceId)
    {
        selectedPlayer.store(0);
        twoPlayerActive.store(false);
        primaryRomPath.clear();
        primarySavePath.clear();
        MPInterface::Set(MPInterface_Dummy);
        cameraHandler = androidCameraHandler;
        eventMessenger = androidEventMessenger;
        RetroAchievements::RetroAchievementsManager::EventMessenger = androidEventMessenger;

        auto instanceArgs = BuildArgsFromConfiguration(*currentConfiguration, instanceId);
        if (!instanceArgs.has_value())
        {
            // TODO: Handle this somehow?
            std::lock_guard lock(playerMutex);
            instance = nullptr;
            return;
        }
        auto nextInstance = std::make_shared<MelonInstance>(
            instanceId,
            currentConfiguration,
            std::move(instanceArgs.value()),
            net,
            std::make_unique<ScreenshotRenderer>(screenshotBufferPointer),
            currentConfiguration->consoleType
        );
        {
            std::lock_guard lock(playerMutex);
            instance = std::move(nextInstance);
        }

        setupAudio(currentConfiguration->audioSettings);
        setAudioActiveInstance(instance);
    }

    void setCodeList(std::list<Cheat> cheats)
    {
        std::lock_guard featureLock(featureMutationMutex);
        if (!isTwoPlayerActive() && instance)
            instance->loadCheats(std::move(cheats));
    }

    void setupAchievements(
        std::list<RetroAchievements::RAAchievement> achievements,
        std::list<RetroAchievements::RALeaderboard> leaderboards,
        std::optional<std::string> richPresenceScript
    )
    {
        std::lock_guard featureLock(featureMutationMutex);
        if (!isTwoPlayerActive() && instance)
            instance->setupAchievements(std::move(achievements), std::move(leaderboards), std::move(richPresenceScript));
    }

    void unloadRetroAchievementsData()
    {
        std::lock_guard featureLock(featureMutationMutex);
        if (!isTwoPlayerActive() && instance)
            instance->unloadRetroAchievementsData();
    }

    std::string getRichPresenceStatus()
    {
        // Status polling may originate on Main. Never queue it behind ROM I/O.
        std::unique_lock featureLock(featureMutationMutex, std::try_to_lock);
        if (!featureLock.owns_lock() || isTwoPlayerActive()) return "";
        return instance ? instance->getRichPresenceStatus() : "";
    }

    std::vector<RetroAchievements::RARuntimeAchievement> getRuntimeAchievements()
    {
        std::unique_lock featureLock(featureMutationMutex, std::try_to_lock);
        if (!featureLock.owns_lock() || isTwoPlayerActive()) return {};
        return instance ? instance->getRuntimeAchievements() : std::vector<RetroAchievements::RARuntimeAchievement>{};
    }

    /**
     * Used to update the emulator's configuration during runtime. Will only update the configurations that can actually change during runtime without causing issues,
     *
     * @param emulatorConfiguration The new emulator configuration
     */
    void updateEmulatorConfiguration(std::unique_ptr<EmulatorConfiguration> emulatorConfiguration) {
        std::lock_guard featureLock(featureMutationMutex);
        if (isTwoPlayerActive()) return;
        std::shared_ptr<EmulatorConfiguration> sharedConfig = std::move(emulatorConfiguration);
        instance->updateConfiguration(sharedConfig);
        updateAudioSettings(sharedConfig->audioSettings);

        currentConfiguration = sharedConfig;
    }

    int loadRom(std::string romPath, std::string sramPath, RomGbaSlotConfig* gbaSlotConfig)
    {
        if (!instance || !instance->loadRom(romPath, sramPath))
            return 2;
        primaryRomPath = romPath;
        primarySavePath = sramPath;

        if (gbaSlotConfig->type == GBA_ROM)
        {
            RomGbaSlotConfigGbaRom* gbaRomConfig = (RomGbaSlotConfigGbaRom*) gbaSlotConfig;
            if (!instance->loadGbaRom(gbaRomConfig->romPath, gbaRomConfig->savePath))
                return 1;
        }
        else if (gbaSlotConfig->type == RUMBLE_PAK)
        {
            instance->loadRumblePak();
        }
        else if (gbaSlotConfig->type == MEMORY_EXPANSION)
        {
            instance->loadGbaMemoryExpansion();
        }

        return 0;
    }

    int bootFirmware()
    {
        // TODO: Maybe validate BIOS and firmware?
        if (instance->bootFirmware())
            return ROMManager::SUCCESS;
        else
            return ROMManager::FIRMWARE_NOT_BOOTABLE;
    }

    void touchScreen(u16 x, u16 y)
    {
        if (auto target = visibleInstance())
            target->touchScreen(x, y);
    }

    void releaseScreen()
    {
        if (auto target = visibleInstance())
            target->releaseScreen();
    }

    void pressKey(u32 key)
    {
        if (auto target = visibleInstance())
            target->pressKey(key);
    }

    void releaseKey(u32 key)
    {
        if (auto target = visibleInstance())
            target->releaseKey(key);
    }

    void start()
    {
        startAudio();
        setupOpenGlContext();

        instance->start();
    }

    u32 loop()
    {
        MPInterface::Get().Process();
        return instance->runFrame();
    }

    Frame* getPresentationFrame(std::optional<std::chrono::time_point<std::chrono::steady_clock>> deadline)
    {
        auto target = visibleInstance();
        return target ? target->getPresentationFrame(deadline) : nullptr;
    }

    void pause()
    {
        std::lock_guard controlLock(peerControlMutex);
        pauseSecondPlayer();
        pauseAudio();
    }

    void resume()
    {
        std::lock_guard controlLock(peerControlMutex);
        if (secondSession) {
            std::lock_guard lock(secondSession->mutex);
            if (!secondSession->failed && !secondSession->finished) {
                secondSession->pauseRequested = false;
                // Only the worker changes its acknowledged paused state. A rapid
                // resume/pause before it wakes must not leave both callers waiting.
                secondSession->condition.notify_all();
            }
        }
        startAudio();
    }

    void reset()
    {
        if (isTwoPlayerActive()) return;
        instance->reset();
    }

    bool saveState(const char* path)
    {
        if (isTwoPlayerActive()) return false;
        Platform::FileHandle* saveStateFile = Platform::OpenFile(path, Platform::FileMode::Write);

        if (!saveStateFile)
            return false;

        Savestate state;
        if (state.Error)
        {
            Platform::CloseFile(saveStateFile);
            return false;
        }

        instance->saveState(&state);

        if (state.Error)
        {
            Platform::CloseFile(saveStateFile);
            return false;
        }

        if (Platform::FileWrite(state.Buffer(), state.Length(), 1, saveStateFile) == 0)
        {
            Platform::Log(Platform::Error, "Failed to write %d-byte savestate to %s\n", state.Length(), path);
            Platform::CloseFile(saveStateFile);
            return false;
        }

        Platform::CloseFile(saveStateFile);
        return true;
    }

    bool loadState(const char* path)
    {
        if (isTwoPlayerActive()) return false;
        auto saveStateFile = Platform::OpenFile(path, Platform::FileMode::Read);
        if (!saveStateFile)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to open state file \"%s\"\n", path);
            return false;
        }

        std::unique_ptr<Savestate> backup = std::make_unique<Savestate>(Savestate::DEFAULT_SIZE);
        if (backup->Error)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to allocate memory for state backup\n");
            Platform::CloseFile(saveStateFile);
            return false;
        }

        if (!instance->saveState(backup.get()) || backup->Error)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to back up state, aborting load (from \"%s\")\n", path);
            Platform::CloseFile(saveStateFile);
            return false;
        }

        size_t size = Platform::FileLength(saveStateFile);

        // Allocate exactly as much memory as we need for the savestate
        std::vector<u8> buffer(size);
        if (Platform::FileRead(buffer.data(), size, 1, saveStateFile) == 0)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to read %u-byte state file \"%s\"\n", size, path);
            Platform::CloseFile(saveStateFile);
            return false;
        }
        Platform::CloseFile(saveStateFile);

        std::unique_ptr<Savestate> state = std::make_unique<Savestate>(buffer.data(), size, false);

        if (!instance->loadState(state.get()) || state->Error)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to load state file \"%s\" into emulator\n", path);
            // Restore backup
            if (!instance->loadState(backup.get()) || state->Error)
                Platform::Log(Platform::LogLevel::Error, "Failed to load backup state\n", path);
            else
                Platform::Log(Platform::LogLevel::Info, "Backup state loaded\n", path);

            return false;
        }
        return true;
    }

    bool loadRewindState(melonDS::RewindSaveState rewindSaveState)
    {
        if (isTwoPlayerActive()) return false;
        std::unique_ptr<Savestate> backup = std::make_unique<Savestate>(Savestate::DEFAULT_SIZE);
        if (backup->Error)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to allocate memory for state backup");
            return false;
        }

        if (!instance->saveState(backup.get()) || backup->Error)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to back up state, aborting rewind state load");
            return false;
        }

        bool result = instance->loadRewindState(rewindSaveState);
        if (!result)
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to load rewind state");
            // Restore backup
            if (!instance->loadState(backup.get()) || backup->Error)
                Platform::Log(Platform::LogLevel::Error, "Failed to load backup state");
            else
                Platform::Log(Platform::LogLevel::Info, "Backup state loaded");
        }

        return result;
    }

    RewindWindow getRewindWindow()
    {
        if (isTwoPlayerActive()) return RewindWindow{};
        return instance->getRewindWindow();
    }

    bool takeScreenshot()
    {
        if (isTwoPlayerActive()) return false;
        if (instance)
            return instance->takeScreenshot();

        return false;
    }

    void stop()
    {
        setAudioActiveInstance(instance);
        stopSecondPlayer();
        MPInterface::Get().End(0);
        std::lock_guard featureLock(featureMutationMutex);
        if (instance) instance->stop();
        cleanupOpenGlContext();
    }

    void cleanup()
    {
        cleanupAudio();
        stopSecondPlayer();
        std::lock_guard featureLock(featureMutationMutex);
        {
            std::lock_guard lock(playerMutex);
            instance = nullptr;
        }
        MPInterface::Set(MPInterface_Dummy);
        primaryRomPath.clear();
        primarySavePath.clear();
        eventMessenger = nullptr;
    }

    bool setupOpenGlContext()
    {
        if (openGlContext == nullptr)
            return false;

        if (!openGlContext->Use())
        {
            Platform::Log(Platform::LogLevel::Error, "Failed to use OpenGL context");
            return false;
        }

        return true;
    }

    void cleanupOpenGlContext()
    {
        if (openGlContext == nullptr)
            return;

        openGlContext->Release();
    }
}

