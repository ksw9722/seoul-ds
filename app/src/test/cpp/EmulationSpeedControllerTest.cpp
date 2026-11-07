// Host-only speed-control tests. No Android device, ROM or BIOS is used.
#include "../../main/cpp/EmulationSpeedController.h"
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

void startsAtNormalSpeed() {
    EmulationSpeedController speed;
    CHECK(speed.current() == 1);
    CHECK(speed.timing().targetFps == 60);
    CHECK(speed.timing().targetWorkDurationNs == 16666666);
}

void cyclesAllFiveSpeedsAndWrapsRepeatedly() {
    EmulationSpeedController speed;
    for (int i = 0; i < 100; ++i) {
        for (int expected : {2, 3, 4, 5, 1}) {
            CHECK(speed.cycle() == expected);
            CHECK(speed.current() == expected);
        }
    }
}

void oneSnapshotKeepsFpsAndHintConsistent() {
    EmulationSpeedController speed;
    for (int expected = 1; expected <= 5; ++expected) {
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
    for (int target = 1; target <= 5; ++target) {
        speed.reset();
        for (int i = 1; i < target; ++i) speed.cycle();
        CHECK(speed.current() == target);
        speed.reset();
        CHECK(speed.current() == 1);
        CHECK(speed.cycle() == 2);
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
                CHECK(current >= 1 && current <= 5);
                const auto timing = speed.timing();
                CHECK(timing.multiplier >= 1 && timing.multiplier <= 5);
                CHECK(timing.targetFps == timing.multiplier * 60);
                CHECK(timing.targetWorkDurationNs == 16666666 / timing.multiplier);
            }
        });
    }
    start.store(true);
    for (auto& writer : writers) writer.join();
    CHECK(speed.current() == 1 + (threads * steps) % 5);
}

void concurrentResetsRemainInRange() {
    EmulationSpeedController speed;
    std::thread resetter([&] {
        for (int i = 0; i < 100000; ++i) speed.reset();
    });
    for (int i = 0; i < 100000; ++i) {
        const auto current = speed.cycle();
        CHECK(current >= 1 && current <= 5);
    }
    resetter.join();
    speed.reset();
    CHECK(speed.current() == 1);
}

int main() {
    startsAtNormalSpeed();
    cyclesAllFiveSpeedsAndWrapsRepeatedly();
    oneSnapshotKeepsFpsAndHintConsistent();
    resettingSessionsReturnsToNormal();
    concurrentRequestsDoNotLoseSteps();
    concurrentResetsRemainInRange();
    std::cout << "PASS: 6 emulation speed cases\n";
}
