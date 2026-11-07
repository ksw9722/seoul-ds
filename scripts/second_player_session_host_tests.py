#!/usr/bin/env python3
"""Exercise the actual Android peer scheduler with fake core/EGL dependencies.

This verifies lifecycle synchronization only, not Android rendering or game trades.
"""
from pathlib import Path
import subprocess
import tempfile
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def block(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[start:index + 1]
    raise ValueError(f"Unterminated block: {marker}")


def main() -> None:
    compiler = shutil.which("g++")
    if not compiler:
        print("BLOCKED: g++ required", file=sys.stderr)
        raise SystemExit(2)
    source = (ROOT / "melonDS-android-lib/src/android/MelonDS.cpp").read_text()
    functions = "\n\n".join(block(source, marker) for marker in (
        "void runSecondPlayer(", "void pauseSecondPlayer()", "void stopSecondPlayer()",
        "void pause()", "void resume()",
    ))
    session = block(source, "struct SecondPlayerSession {") + ";"
    program = r'''
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <exception>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
using u32 = uint32_t;
using namespace std::chrono_literals;
static std::atomic_bool graphicsOkay{true};
static std::atomic_int contextsDestroyed{0};
struct OpenGLContext {
    bool InitContext(long) { return graphicsOkay.load(); }
    bool Use() { return true; }
    void Release() {}
    void DeInit() { ++contextsDestroyed; }
};
constexpr int GL_NO_ERROR = 0;
int glGetError() { return GL_NO_ERROR; }
namespace Platform {
    enum { Error, Unknown };
    template <typename... T> void Log(int, const char*, T...) {}
}
struct MPInterface {
    static MPInterface& Get() { static MPInterface value; return value; }
    void End(int) {}
};
struct Messenger {
    std::atomic_int errors{0};
    void onEmulatorStop(int) { ++errors; }
};
auto eventMessenger = std::make_shared<Messenger>();
struct MelonInstance {
    std::atomic_int starts{0}, frames{0}, stops{0};
    std::atomic_bool failFrame{false};
    void start() { ++starts; }
    u32 runFrame() {
        if (failFrame.load()) throw std::runtime_error("test frame failure");
        ++frames;
        std::this_thread::sleep_for(1ms);
        return 263;
    }
    void stop() { ++stops; }
};
std::mutex playerMutex, peerControlMutex;
std::shared_ptr<MelonInstance> secondInstance;
std::atomic_int selectedPlayer{0};
std::atomic_bool twoPlayerActive{false};
void pauseAudio() {}
void startAudio() {}
''' + session + r'''
std::unique_ptr<SecondPlayerSession> secondSession;
''' + functions + r'''
void require(bool okay, const char* message) {
    if (!okay) throw std::runtime_error(message);
}
template <typename Predicate> void eventually(Predicate predicate) {
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while (!predicate()) {
        require(std::chrono::steady_clock::now() < deadline, "timed out");
        std::this_thread::sleep_for(1ms);
    }
}
std::shared_ptr<MelonInstance> launch() {
    secondSession = std::make_unique<SecondPlayerSession>();
    secondSession->player = std::make_shared<MelonInstance>();
    auto player = secondSession->player;
    secondSession->worker = std::thread(runSecondPlayer, secondSession.get(), 1);
    std::unique_lock lock(secondSession->mutex);
    secondSession->condition.wait(lock, [] { return secondSession->initialized; });
    return player;
}
int main() {
    {
        auto player = launch();
        require(secondSession->initializationSucceeded, "initialization failed");
        require(player->frames == 0, "peer ran before resume");
        resume();
        eventually([&] { return player->frames > 0; });
        pause();
        const int frames = player->frames;
        std::this_thread::sleep_for(25ms);
        require(player->frames == frames, "frame ran after acknowledged pause");
        for (int i = 0; i < 1000; ++i) { resume(); pause(); }
        stopSecondPlayer();
        require(player->stops == 1 && !secondSession, "shutdown was incomplete");
        std::cout << "PASS: paused start, frame pause, 1000 rapid resume/pause cycles, join\n";
    }
    {
        const int oldContexts = contextsDestroyed;
        auto player = launch();
        player->failFrame = true;
        resume();
        eventually([] { return eventMessenger->errors > 0; });
        pause();
        require(player->stops == 0 && contextsDestroyed == oldContexts,
                "failed worker destroyed resources before presentation exclusion");
        for (int i = 0; i < 100; ++i) { resume(); pause(); }
        stopSecondPlayer();
        require(player->stops == 1 && contextsDestroyed == oldContexts + 1,
                "failed worker did not clean up during normal stop");
        std::cout << "PASS: failure retains render resources, pause remains safe, stop cleans\n";
    }
    {
        graphicsOkay = false;
        auto player = launch();
        require(!secondSession->initializationSucceeded, "false graphics startup success");
        stopSecondPlayer();
        require(player->starts == 0 && player->frames == 0, "core ran after graphics failure");
        std::cout << "PASS: graphics startup failure never runs the peer\n";
    }
}
'''
    with tempfile.TemporaryDirectory(prefix="seoul-peer-session-") as directory:
        cpp = Path(directory) / "test.cpp"
        cpp.write_text(program)
        for profile, flags in (("debug", ["-O0"]), ("release", ["-O2", "-DNDEBUG"])):
            binary = Path(directory) / profile
            print(f"PROFILE: {profile}", flush=True)
            subprocess.run([compiler, "-std=c++17", "-pthread", *flags, str(cpp), "-o", str(binary)], check=True, timeout=120)
            subprocess.run([str(binary)], check=True, timeout=20)


if __name__ == "__main__":
    main()
