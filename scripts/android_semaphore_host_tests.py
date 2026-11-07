#!/usr/bin/env python3
"""Compile the actual Android pthread semaphore functions on host (no Android SDK)."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
root = Path(__file__).resolve().parents[1]
source = (root / "melonDS-android-lib/src/android/PlatformAndroid.cpp").read_text()
start = source.index("    Semaphore* Semaphore_Create()")
end = source.index("    Mutex* Mutex_Create()", start)
preamble = r'''
#include <pthread.h>
#include <cstdlib>
#include <cerrno>
#include <chrono>
#include <thread>
#include <cstdio>
#include "TimeoutDeadline.h"
struct Semaphore;
struct AndroidSemaphore { pthread_mutex_t mutex; pthread_cond_t cond; int val; };
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"CHECK line %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
'''
test = r'''
int main() {
    auto deadline = AddMillisecondsToDeadline(timespec{100, 999000000}, 25);
    CHECK(deadline.tv_sec == 101 && deadline.tv_nsec == 24000000);
    deadline = AddMillisecondsToDeadline(timespec{100, 1000000}, 2500);
    CHECK(deadline.tv_sec == 102 && deadline.tv_nsec == 501000000);
    Semaphore* sem = Semaphore_Create();
    CHECK(!Semaphore_TryWait(sem, 0));
    Semaphore_Post(sem, 1); // zero-time wait must release the mutex
    CHECK(Semaphore_TryWait(sem, 0));
    auto start = std::chrono::steady_clock::now();
    CHECK(!Semaphore_TryWait(sem, 25));
    CHECK(std::chrono::steady_clock::now() - start >= std::chrono::milliseconds(15));
    Semaphore_Post(sem, 1); // timed-out wait must release the mutex
    CHECK(Semaphore_TryWait(sem, 0));
    std::thread poster([&] { std::this_thread::sleep_for(std::chrono::milliseconds(20)); Semaphore_Post(sem, 1); });
    CHECK(Semaphore_TryWait(sem, 1000));
    poster.join();
    Semaphore_Post(sem, 2); Semaphore_Reset(sem);
    CHECK(!Semaphore_TryWait(sem, 0));
    Semaphore_Free(sem);
    std::puts("PASS: actual Android semaphore deadlines, timeout, unlock, wake and reset");
}
'''
compiler = shutil.which("g++")
if not compiler:
    print("BLOCKED: g++ required", file=sys.stderr)
    raise SystemExit(2)
with tempfile.TemporaryDirectory(prefix="seoul-ds-semaphore-") as tmp:
    path = Path(tmp) / "test.cpp"
    path.write_text(preamble + source[start:end] + test)
    for profile, flags in (("debug", ["-O0"]), ("release", ["-O2", "-DNDEBUG"])):
        binary = Path(tmp) / profile
        subprocess.run([compiler, "-std=c++17", "-pthread", *flags, "-I", str(root / "melonDS-android-lib/src/android"), str(path), "-o", str(binary)], check=True, timeout=120)
        print(f"PROFILE: {profile}", flush=True)
        subprocess.run([str(binary)], check=True, timeout=10)
