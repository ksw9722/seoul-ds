#ifndef SEOUL_DS_EMULATION_SPEED_CONTROLLER_H
#define SEOUL_DS_EMULATION_SPEED_CONTROLLER_H

#include <atomic>
#include <cstdint>

// The UI publishes requests only. Frame pacing and performance hints are applied together
// by the emulation thread, so changing speed cannot race hint-session creation/destruction.
class EmulationSpeedController {
public:
    static constexpr int NORMAL_SPEED = 1;
    static constexpr int FAST_SPEED = 5;
    static constexpr int MAX_SPEED = 10;
    static constexpr int BASE_FPS = 60;
    static constexpr int64_t BASE_FRAME_DURATION_NS = 16666666;

    struct Timing {
        int multiplier;
        int targetFps;
        int64_t targetWorkDurationNs;
    };

    int current() const {
        return multiplier.load(std::memory_order_relaxed);
    }

    int cycle() {
        int previous = current();
        int next;
        do {
            switch (previous) {
                case NORMAL_SPEED: next = FAST_SPEED; break;
                case FAST_SPEED: next = MAX_SPEED; break;
                default: next = NORMAL_SPEED; break;
            }
        } while (!multiplier.compare_exchange_weak(previous, next, std::memory_order_relaxed));
        return next;
    }

    void reset() {
        multiplier.store(NORMAL_SPEED, std::memory_order_relaxed);
    }

    Timing timing() const {
        const int speed = current();
        return {speed, BASE_FPS * speed, BASE_FRAME_DURATION_NS / speed};
    }

private:
    std::atomic<int> multiplier{NORMAL_SPEED};
};

#endif
