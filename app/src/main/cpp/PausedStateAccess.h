// Seoul DS modification, 2026. GPL-3.0-or-later; see the repository LICENSE.
#pragma once

#include <atomic>
#include <cerrno>
#include <chrono>
#include <mutex>
#include <pthread.h>
#include <time.h>

/**
 * Excludes native session teardown and waits for a frame-boundary pause before touching state.
 * Lock order is always operationMutex -> threadMutex. The emulation thread only takes threadMutex.
 * This guard is used on a background dispatcher, never around screenshot capture (which needs a
 * future frame). A failed/late pause returns false instead of touching a running emulator.
 */
class PausedStateAccess {
public:
    PausedStateAccess(
        std::mutex& operationMutex,
        pthread_mutex_t& threadMutex,
        pthread_cond_t& threadCondition,
        const bool& started,
        const bool& stopping,
        const bool& paused,
        const std::atomic_bool& reallyPaused,
        std::chrono::milliseconds timeout = std::chrono::seconds(5)
    ) : operationLock(operationMutex), threadMutex(threadMutex) {
        // A stopped session has destroyed its pthread synchronization objects.
        if (!started) return;

        pthread_mutex_lock(&threadMutex);
        threadLocked = true;
        if (stopping || !paused) return;

        timespec deadline{};
        clock_gettime(CLOCK_REALTIME, &deadline);
        const auto timeoutNs = std::chrono::duration_cast<std::chrono::nanoseconds>(timeout).count();
        deadline.tv_sec += timeoutNs / 1000000000;
        deadline.tv_nsec += timeoutNs % 1000000000;
        if (deadline.tv_nsec >= 1000000000) {
            ++deadline.tv_sec;
            deadline.tv_nsec -= 1000000000;
        }

        while (paused && !stopping && !reallyPaused.load()) {
            const int result = pthread_cond_timedwait(&threadCondition, &threadMutex, &deadline);
            if (result != 0) return;
        }
        ready = paused && !stopping && reallyPaused.load();
    }

    ~PausedStateAccess() {
        if (threadLocked) pthread_mutex_unlock(&threadMutex);
    }

    PausedStateAccess(const PausedStateAccess&) = delete;
    PausedStateAccess& operator=(const PausedStateAccess&) = delete;

    explicit operator bool() const { return ready; }

private:
    std::unique_lock<std::mutex> operationLock;
    pthread_mutex_t& threadMutex;
    bool threadLocked = false;
    bool ready = false;
};
