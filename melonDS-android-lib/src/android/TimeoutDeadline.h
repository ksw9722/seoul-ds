// Seoul DS modification, 2026. GPL-3.0-or-later; see the repository LICENSE.
#pragma once

#include <time.h>
#include <cstdint>

// pthread_cond_timedwait uses an absolute deadline in the condition's clock.
// Android semaphores use the default CLOCK_REALTIME condition attribute.
inline timespec AddMillisecondsToDeadline(timespec now, int milliseconds)
{
    const int64_t nanoseconds = static_cast<int64_t>(milliseconds) * 1000000;
    now.tv_sec += nanoseconds / 1000000000;
    now.tv_nsec += nanoseconds % 1000000000;
    if (now.tv_nsec >= 1000000000) {
        ++now.tv_sec;
        now.tv_nsec -= 1000000000;
    }
    return now;
}
