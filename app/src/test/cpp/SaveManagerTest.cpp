// Synthetic save data and fake file errors; no user/game save is loaded.
#include <atomic>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "SaveManager.h"
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"CHECK line %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
namespace { bool failOpen = false, failWrite = false, failFlush = false, failClose = false; std::vector<melonDS::u8> disk; }
namespace melonDS::Platform {
struct Mutex { std::mutex value; };
struct Thread { std::thread value; explicit Thread(std::function<void()> fn):value(std::move(fn)){} };
struct FileHandle {};
Mutex* Mutex_Create() { return new Mutex; }
void Mutex_Free(Mutex* m) { delete m; }
void Mutex_Lock(Mutex* m) { m->value.lock(); }
void Mutex_Unlock(Mutex* m) { m->value.unlock(); }
Thread* Thread_Create(std::function<void()> fn) { return new Thread(std::move(fn)); }
void Thread_Wait(Thread* t) { if(t && t->value.joinable()) t->value.join(); }
void Thread_Free(Thread* t) { delete t; }
void Sleep(u64 us) { std::this_thread::sleep_for(std::chrono::microseconds(us)); }
void Log(LogLevel, const char*, ...) {}
FileHandle* OpenFile(const std::string&, FileMode) { return failOpen ? nullptr : new FileHandle; }
bool CloseFile(FileHandle* f) { delete f; return !failClose; }
bool FileFlush(FileHandle*) { return !failFlush; }
u64 FileWrite(const void* data, u64 size, u64 count, FileHandle*) {
    if (failWrite) return 0;
    auto* bytes = static_cast<const u8*>(data); disk.assign(bytes, bytes + size * count); return count;
}
u64 FileRead(void* data, u64 size, u64 count, FileHandle*) { std::memcpy(data, disk.data(), size*count); return count; }
u64 FileLength(FileHandle*) { return disk.size(); }
}
int main() {
    SaveManager save("synthetic-path");
    melonDS::u8 bytes[] = {0x12,0x34,0x56,0x78};
    save.RequestFlush(bytes, 4, 0, 4); save.CheckFlush();
    CHECK(save.NeedsFlush());
    for (bool* failure : {&failOpen, &failWrite, &failFlush, &failClose}) {
        *failure = true; CHECK(!save.FlushSecondaryBuffer()); CHECK(save.NeedsFlush()); *failure = false;
    }
    CHECK(save.FlushSecondaryBuffer()); CHECK(!save.NeedsFlush());
    CHECK(disk == std::vector<melonDS::u8>(bytes,bytes+4));
    bytes[2]=0xff; save.RequestFlush(bytes,4,2,1); save.CheckFlush();
    melonDS::u8 copy[4]{};
    CHECK(!save.FlushSecondaryBuffer(copy,3));
    CHECK(save.FlushSecondaryBuffer(copy,4)); CHECK(copy[2]==0xff);
    CHECK(save.NeedsFlush()); // exporting to memory must not hide pending disk write
    CHECK(save.FlushSecondaryBuffer()); CHECK(disk[2]==0xff);
    std::puts("PASS: save flush, file errors remain pending, retry, partial update and memory export");
}
