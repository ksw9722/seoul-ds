// Host-only synchronization tests. No emulator, Android device, ROM or BIOS is used.
#include "../../main/cpp/PausedStateAccess.h"
#include <cstdlib>
#include <future>
#include <iostream>
#include <thread>

// Do not use assert: these checks and side effects must survive -DNDEBUG.
#define CHECK(condition) do { \
    if (!(condition)) { \
        std::cerr << "CHECK failed at line " << __LINE__ << ": " << #condition << "\n"; \
        std::abort(); \
    } \
} while (false)

using namespace std::chrono_literals;

struct Fixture {
    std::mutex operationMutex;
    pthread_mutex_t threadMutex = PTHREAD_MUTEX_INITIALIZER;
    pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
    bool started = true;
    bool stopping = false;
    bool paused = true;
    std::atomic_bool acknowledged = false;

    ~Fixture() {
        pthread_cond_destroy(&condition);
        pthread_mutex_destroy(&threadMutex);
    }

    PausedStateAccess guard(std::chrono::milliseconds timeout = 1s) {
        return {operationMutex, threadMutex, condition, started, stopping, paused, acknowledged, timeout};
    }
};

void rejectsStoppedRunningAndStoppingSessions() {
    Fixture f;
    f.started = false;
    { auto access = f.guard(); CHECK(!access); }
    f.started = true;
    f.paused = false;
    { auto access = f.guard(); CHECK(!access); }
    f.paused = true;
    f.stopping = true;
    { auto access = f.guard(); CHECK(!access); }
}

void waitsForFrameBoundaryAcknowledgement() {
    Fixture f;
    std::promise<void> attemptingAccess;
    auto result = std::async(std::launch::async, [&] {
        attemptingAccess.set_value();
        auto access = f.guard();
        return bool(access);
    });
    attemptingAccess.get_future().wait();
    // The access must remain pending until a real frame-boundary acknowledgement arrives.
    CHECK(result.wait_for(30ms) == std::future_status::timeout);
    pthread_mutex_lock(&f.threadMutex);
    f.acknowledged = true;
    pthread_cond_broadcast(&f.condition);
    pthread_mutex_unlock(&f.threadMutex);
    CHECK(result.wait_for(2s) == std::future_status::ready);
    CHECK(result.get());
}

void resumedBeforeAcknowledgementFailsSafely() {
    Fixture f;
    auto result = std::async(std::launch::async, [&] { auto access = f.guard(); return bool(access); });
    pthread_mutex_lock(&f.threadMutex);
    f.paused = false;
    pthread_cond_broadcast(&f.condition);
    pthread_mutex_unlock(&f.threadMutex);
    CHECK(result.wait_for(2s) == std::future_status::ready);
    CHECK(!result.get());
}

void missingAcknowledgementTimesOutAndReleasesLocks() {
    Fixture f;
    const auto start = std::chrono::steady_clock::now();
    { auto access = f.guard(20ms); CHECK(!access); }
    CHECK(std::chrono::steady_clock::now() - start < 2s);
    CHECK(f.operationMutex.try_lock());
    f.operationMutex.unlock();
    CHECK(pthread_mutex_trylock(&f.threadMutex) == 0);
    pthread_mutex_unlock(&f.threadMutex);
}

void teardownWaitsForStateAccessAndThenProceeds() {
    Fixture f;
    f.acknowledged = true;
    std::promise<void> accessReady;
    std::promise<void> releaseAccess;
    auto release = releaseAccess.get_future();
    std::atomic_int sequence = 0;
    std::atomic_int accessFinished = 0;
    std::atomic_int teardownStarted = 0;
    auto state = std::async(std::launch::async, [&] {
        auto access = f.guard();
        CHECK(access);
        accessReady.set_value();
        release.wait();
        accessFinished = ++sequence;
    });
    accessReady.get_future().wait();
    std::promise<void> attemptingTeardown;
    auto teardown = std::async(std::launch::async, [&] {
        attemptingTeardown.set_value();
        std::lock_guard<std::mutex> lock(f.operationMutex);
        teardownStarted = ++sequence;
        pthread_mutex_lock(&f.threadMutex);
        f.stopping = true;
        f.started = false;
        pthread_cond_broadcast(&f.condition);
        pthread_mutex_unlock(&f.threadMutex);
    });
    attemptingTeardown.get_future().wait();
    CHECK(teardown.wait_for(30ms) == std::future_status::timeout);
    CHECK(teardownStarted == 0);
    releaseAccess.set_value();
    CHECK(state.wait_for(2s) == std::future_status::ready);
    CHECK(teardown.wait_for(2s) == std::future_status::ready);
    state.get();
    teardown.get();
    CHECK(accessFinished == 1);
    CHECK(teardownStarted == 2);
    { auto access = f.guard(); CHECK(!access); }
}

int main() {
    rejectsStoppedRunningAndStoppingSessions();
    waitsForFrameBoundaryAcknowledgement();
    resumedBeforeAcknowledgementFailsSafely();
    missingAcknowledgementTimesOutAndReleasesLocks();
    teardownWaitsForStateAccessAndThenProceeds();
    std::cout << "PASS: 5 native pause/state-access host tests\n";
}
