// Synthetic transport tests only: no ROM, game compatibility or Android execution.
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include "LocalMP.h"
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #x); std::abort(); } } while (0)
namespace melonDS::Platform {
struct Mutex { std::mutex value; };
struct Semaphore { std::mutex mutex; std::condition_variable cv; int count = 0; };
Mutex* Mutex_Create() { return new Mutex; }
void Mutex_Free(Mutex* m) { delete m; }
void Mutex_Lock(Mutex* m) { m->value.lock(); }
void Mutex_Unlock(Mutex* m) { m->value.unlock(); }
Semaphore* Semaphore_Create() { return new Semaphore; }
void Semaphore_Free(Semaphore* s) { delete s; }
void Semaphore_Reset(Semaphore* s) { std::lock_guard lock(s->mutex); s->count = 0; }
void Semaphore_Post(Semaphore* s, int n) { std::lock_guard lock(s->mutex); s->count += n; s->cv.notify_all(); }
bool Semaphore_TryWait(Semaphore* s, int ms) {
    std::unique_lock lock(s->mutex);
    if (!s->cv.wait_for(lock, std::chrono::milliseconds(ms), [&]{ return s->count > 0; })) return false;
    --s->count; return true;
}
void Log(LogLevel, const char*, ...) {}
}
int main() {
    melonDS::LocalMP mp;
    mp.SetRecvTimeout(100);
    std::array<melonDS::u8, 2400> in{}, out{};
    melonDS::u64 timestamp = 0;
    in[0] = 0x42; in[1] = 0x7a;
    mp.Begin(0); mp.Begin(1);
    CHECK(mp.SendPacket(0, in.data(), 2, 100) == 2);
    CHECK(mp.RecvPacket(0, out.data(), &timestamp) == 0); // no self echo
    CHECK(mp.RecvPacket(1, out.data(), &timestamp) == 2);
    CHECK(timestamp == 100 && out[0] == 0x42 && out[1] == 0x7a);
    CHECK(mp.RecvPacket(1, out.data(), &timestamp) == 0);
    std::puts("PASS: delivery, timestamp, no self echo and empty queue");
    for (int i = 0; i < 3000; ++i) {
        CHECK(mp.SendPacket(1, in.data(), 100, 200 + i) == 100);
        CHECK(mp.RecvPacket(0, out.data(), &timestamp) == 100);
        CHECK(mp.RecvPacket(1, out.data(), &timestamp) == 0);
        CHECK(timestamp == static_cast<melonDS::u64>(200 + i));
    }
    std::puts("PASS: FIFO wraparound");
    CHECK(mp.SendPacket(0, in.data(), melonDS::kMaxFrameSize + 1, 9000) == 0);
    CHECK(mp.SendCmd(0, in.data(), 2, 10000) == 2);
    CHECK(mp.RecvHostPacket(1, out.data(), &timestamp) == 2);
    CHECK(timestamp == 10000);
    std::thread peer([&] { CHECK(mp.SendReply(1, in.data(), 2, 10000, 1) == 2); });
    std::array<melonDS::u8, 15 * 1024> replies{};
    CHECK(mp.RecvReplies(0, replies.data(), 10000, 2) == 2);
    peer.join();
    CHECK(replies[0] == 0x42 && replies[1] == 0x7a);
    CHECK(mp.SendAck(0, in.data(), 2, 10001) == 2);
    CHECK(mp.RecvHostPacket(1, out.data(), &timestamp) == 2);
    std::puts("PASS: command, concurrent reply and acknowledgement");
    mp.End(0);
    CHECK(mp.RecvHostPacket(1, out.data(), &timestamp) == -1);
    mp.End(1); mp.Begin(0); mp.Begin(1);
    CHECK(mp.RecvPacket(0, out.data(), &timestamp) == 0);
    CHECK(mp.RecvPacket(1, out.data(), &timestamp) == 0);
    mp.End(0); mp.End(1);
    std::puts("PASS: disconnect and clean rejoin");
}
