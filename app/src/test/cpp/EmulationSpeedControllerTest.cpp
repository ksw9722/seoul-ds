// Host-only speed-control tests. No Android device, ROM or BIOS is used.
#include "../../main/cpp/EmulationSpeedController.h"
#include <array>
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <vector>

// Always-on checks also verify the optimized NDEBUG profile.
#define CHECK(condition) do { \
    if (!(condition)) { \
        std::cerr << "CHECK failed at line " << __LINE__ << ": " << #condition << "\n"; \
        std::abort(); \
    } \
} while (false)

constexpr std::array<int, 3> EXPECTED_SPEEDS{1, 5, 10};

bool isSupportedSpeed(int speed) {
    return speed == 1 || speed == 5 || speed == 10;
}

void startsAtNormalSpeed() {
    EmulationSpeedController speed;
    CHECK(speed.current() == 1);
    CHECK(speed.timing().targetFps == 60);
    CHECK(speed.timing().targetWorkDurationNs == 16666666);
}

void cyclesRequestedSpeedsAndWrapsRepeatedly() {
    EmulationSpeedController speed;
    for (int i = 0; i < 100; ++i) {
        for (int expected : {5, 10, 1}) {
            CHECK(speed.cycle() == expected);
            CHECK(speed.current() == expected);
        }
    }
}

void oneSnapshotKeepsFpsAndHintConsistent() {
    EmulationSpeedController speed;
    for (int expected : EXPECTED_SPEEDS) {
        const auto timing = speed.timing();
        CHECK(timing.multiplier == expected);
        CHECK(timing.targetFps == 60 * expected);
        CHECK(timing.targetWorkDurationNs == 16666666 / expected);
        CHECK(timing.targetWorkDurationNs > 0);
        speed.cycle();
    }
}

void resettingSessionsReturnsToNormal() {
    EmulationSpeedController speed;
    for (size_t index = 0; index < EXPECTED_SPEEDS.size(); ++index) {
        speed.reset();
        for (size_t i = 0; i < index; ++i) speed.cycle();
        CHECK(speed.current() == EXPECTED_SPEEDS[index]);
        speed.reset();
        CHECK(speed.current() == 1);
        CHECK(speed.cycle() == 5);
    }
}

void concurrentRequestsDoNotLoseSteps() {
    EmulationSpeedController speed;
    constexpr int threads = 8;
    constexpr int steps = 20003;
    std::atomic<bool> start{false};
    std::vector<std::thread> writers;
    for (int i = 0; i < threads; ++i) {
        writers.emplace_back([&] {
            while (!start.load()) std::this_thread::yield();
            for (int step = 0; step < steps; ++step) {
                const auto current = speed.cycle();
                CHECK(isSupportedSpeed(current));
                const auto timing = speed.timing();
                CHECK(isSupportedSpeed(timing.multiplier));
                CHECK(timing.targetFps == timing.multiplier * 60);
                CHECK(timing.targetWorkDurationNs == 16666666 / timing.multiplier);
            }
        });
    }
    start.store(true);
    for (auto& writer : writers) writer.join();
    CHECK(speed.current() == EXPECTED_SPEEDS[(threads * steps) % EXPECTED_SPEEDS.size()]);
}

void concurrentResetsKeepSupportedSpeeds() {
    EmulationSpeedController speed;
    std::thread resetter([&] {
        for (int i = 0; i < 100000; ++i) speed.reset();
    });
    for (int i = 0; i < 100000; ++i) {
        const auto current = speed.cycle();
        CHECK(isSupportedSpeed(current));
    }
    resetter.join();
    speed.reset();
    CHECK(speed.current() == 1);
}

int main() {
    startsAtNormalSpeed();
    cyclesRequestedSpeedsAndWrapsRepeatedly();
    oneSnapshotKeepsFpsAndHintConsistent();
    resettingSessionsReturnsToNormal();
    concurrentRequestsDoNotLoseSteps();
    concurrentResetsKeepSupportedSpeeds();
    std::cout << "PASS: 6 emulation speed cases\n";
}
