# 저장 상태 작업의 수명주기·동시성 검토

## 범위와 발견

기준은 melonDS Android `2.0.1`의 Android 프런트엔드다. 네이티브 코어 서브모듈은 변경하지 않았다. 이 문서는 **저장 상태(save state)** 작업의 안전성 보완을 설명하며, 게임 안의 일반 저장(`.sav`)과 저장 상태를 동일한 것으로 취급하지 않는다.

원본 코드를 읽어 확인한 문제:

1. Quick Save / Quick Load에서 네이티브 함수가 `false`를 반환하면 실패 안내가 없었다.
2. 저장 폴더 접근권한 회수 또는 파일 생성 실패로 발생하는 `SecurityException`, `IOException`, `SaveSlotLoadException`을 저장 경로에서 처리하지 않았다.
3. 저장 중 Activity가 백그라운드로 이동해도 작업이 끝나면 무조건 재개했다.
4. 빠른 연속 입력으로 저장/불러오기 작업이 겹칠 수 있었다.
5. JNI 저장/불러오기는 일시정지 요청만 믿고 실행했으며, 현재 프레임이 실제로 끝났다는 확인을 기다리지 않았다. 종료의 네이티브 정리와 저장 접근도 상호 배제하지 않았다.
6. 두 JNI 함수에서 `GetStringUTFChars`의 문자열을 반환하지 않았다.

## 설계

### Kotlin 정책 계층

`SaveStateOperationCoordinator`는 UI 디스패처에서 호출하는 단일 작업 조정자다.

- 진행 중인 작업이 있으면 추가 입력을 **대기열에 쌓지 않고 무시**한다.
- 외부의 일시정지/재개 의도를 저장 작업 자체의 임시 일시정지와 구분한다.
- 뒤늦게 도착한 Activity 일시정지/메뉴 일시정지가 완료 콜백보다 우선한다.
- 취소는 저장 실패로 바꾸지 않고 전파한다. 취소된 세션은 재개하지 않는다.
- 예상한 문서/저장소 오류만 `false`로 복구한다. 프로그래밍 오류를 무조건 숨기지 않는다.
- 상태 저장 후 오래된 미리보기 삭제 실패는 이미 성공한 저장 상태를 실패나 앱 크래시로 바꾸지 않는다. 새 저장 상태의 자동 미리보기 생성은 아래 수명주기 문제 때문에 알파에서 제외했다.

`EmulatorActivity`는 실제 `onResume` / `onPause`를 ViewModel에 알린다. ViewModel은 백그라운드에서 온 재개 요청을 거절하며, 새 ROM을 같은 Activity에서 실행했을 때도 재개 정책을 다시 설정한다. 저장 슬롯을 선택한 뒤에는 정상적으로 재개하되, 그 이후에 발생한 백그라운드 전환은 그대로 존중한다.

### 네이티브 실행 계층

`AndroidEmulatorManager`의 저장/불러오기/일시정지/재개/초기화/종료 네이티브 호출은 단일 병렬도의 IO 디스패처에서 수행한다. 특히 `stopEmulator`는 suspend 함수이며, UI는 정리가 끝난 뒤 닫힌다. 파일 I/O나 프레임 경계 대기를 UI 스레드에서 수행하지 않는다. 종료를 요청하는 순간 Main 스레드의 입력 허용 조건을 먼저 닫아, 비동기 정리와 새 터치/컨트롤러 입력이 겹치지 않게 한다. 터치 해제도 같은 경로를 사용하며 `ACTION_CANCEL`을 처리한다.

`limitedParallelism(1)`을 suspend 함수 전체에 걸친 잠금이라고 가정하지 않는다. 실제 네이티브 저장/불러오기/정리의 임계구역은 별도의 C++ 잠금으로 보호한다.

`PausedStateAccess`의 순서:

1. `stateOperationMutex`를 획득한다.
2. 세션이 시작되지 않았다면 실패한다. 파괴된 pthread 객체에 접근하지 않는다.
3. `emuThreadMutex`를 획득한다.
4. 일시정지 상태가 아니거나 종료 중이면 실패한다.
5. 에뮬레이션 루프가 프레임을 끝내고 `isThreadReallyPaused`를 설정·broadcast할 때까지 조건변수로 기다린다. 조건변수 대기 중에는 스레드 mutex가 해제되므로 루프가 진행할 수 있다.
6. 기본 5초 이내에 확인되지 않으면 상태에 접근하지 않고 실패한다.
7. 확인 후 저장/불러오기를 수행하고 JNI 문자열을 반환한다.
8. RAII로 스레드 mutex, 작업 mutex 순서로 해제한다.

잠금 순서는 항상 `stateOperationMutex → emuThreadMutex`다. 에뮬레이션 루프는 `emuThreadMutex`만 사용한다. 초기 설정·ROM/펌웨어 로드·시작·종료도 같은 작업 mutex를 사용한다. 종료는 스레드 mutex를 해제한 뒤 `pthread_join`한다. 따라서 저장과 teardown이 동일 상태를 동시에 사용하지 않는다. 화면 표시 JNI도 작업 mutex를 `try_lock`으로 획득하고, 획득하지 못하면 프레임을 건너뛴다. 느린 저장소 때문에 렌더링 스레드가 잠금 대기를 하지 않으면서 정리 중인 프레임 포인터를 사용하지 않도록 한다. 고정 코어의 FrameQueue를 검토한 결과, 표시 프레임은 deadline이 없으면 이전 프레임을 즉시 반환하고, deadline이 있으면 `wait_until`만 사용한다. 생산자는 표시 소비자를 기다리지 않고 오래된 프레임을 재사용하므로 이 잠금 때문에 새 무한 큐 대기가 생기지 않는다.

화면 표시 뒤 생성한 GPU fence도 생산자 컨텍스트에서 `glFlush()`로 제출한다. 다른 컨텍스트의 대기가 생산자 명령을 대신 flush하지 않으므로, 다음 화면 표시가 없는 일시정지 전환에서도 fence가 제출되게 하는 조치다. 이는 명세와 코드 검토에 근거한 보완이며 실제 GPU에서 재현·검증했다고 주장하지 않는다. 근거: [Khronos EGL_KHR_fence_sync](https://registry.khronos.org/EGL/extensions/KHR/EGL_KHR_fence_sync.txt), [EGL_KHR_wait_sync](https://registry.khronos.org/EGL/extensions/KHR/EGL_KHR_wait_sync.txt).

### 알파에서는 저장 상태 자동 미리보기 생성을 하지 않음

업스트림의 외부 스크린샷 캡처는 **다음 에뮬레이션 프레임을 무조건 기다린다**. 종료 정리가 먼저 알림을 보낸 뒤 캡처 함수에 진입하면 알림을 놓칠 수 있고, 대기 스레드와 코어 객체 파괴가 겹칠 수 있다. 단순히 JNI에서 수명주기 잠금을 추가하면 이 늦은 진입 경로에서 오히려 종료 교착이 생긴다.

따라서 이번 알파는 `saveRomState`에서 네이티브 `takeScreenshot` 호출을 제거했다. 실제 저장 상태 데이터는 정상적으로 저장하고, IO 디스패처에서 이전 미리보기만 최선 노력으로 삭제한다. 슬롯 UI는 미리보기가 없으면 기존 placeholder를 표시한다. 이것은 저장 기능 제거가 아니라 **코스메틱 자동 썸네일의 의도적 보류**다. 코어 안에서 실행되는 되감기 캡처는 변경하지 않았다. 안전한 캡처 완료/취소 프로토콜이 업스트림에 마련되고 기기 검증을 마친 뒤 재도입할 수 있다.

수정 후 UI/ViewModel의 네이티브 `takeScreenshot` 호출 경로는 없다. 미사용 인터페이스/JNI 정의는 업스트림 호환을 위해 남아 있으므로 정의가 남아 있다는 사실을 실행 경로가 남았다는 뜻으로 혼동하지 않는다.

## 동시성 검토표

| 상황 | 처리 | 확인 범위 |
|---|---|---|
| 빠른 저장 버튼 연속 입력 | 첫 작업만 실행, 중복 작업은 큐에 넣지 않음 | JVM 정책 테스트 |
| 저장 도중 Home/화면 잠금 | 일시정지 의도 즉시 기록, 완료 후 재개하지 않음 | JVM 정책 테스트; 실제 Activity는 기기 검증 필요 |
| 작업 중 다시 foreground | 완료 시점에 재개 의도가 남아 있을 때만 재개 | JVM 정책 테스트 |
| 세션 취소/ROM 전환 | 취소 전파, gate 해제, 기존 세션 재개 금지 | JVM 정책 테스트; ROM 전환 실기는 미실행 |
| 저장 폴더 접근권한 회수/쓰기 실패 | 실패 안내, 다음 시도 가능 | fake 예외 JVM 테스트; SAF 공급자 실기는 미실행 |
| 일시정지 요청 직후 저장 | 프레임 경계의 실제 pause 확인까지 대기 | 호스트 pthread 테스트 |
| pause 확인 전에 재개됨 | 실행 중인 상태에 접근하지 않고 실패 | 호스트 pthread 테스트 |
| pause 확인 누락 | 5초 제한 후 실패, 잠금 해제 | 짧은 timeout을 주입한 호스트 테스트 |
| 저장 중 종료 | 저장 접근이 끝난 뒤 정리; UI 스레드는 대기하지 않음 | 호스트 상호배제 테스트 + 코드 검토; Android 실기는 미실행 |
| 종료 요청 직후 터치/키 입력 | 동기적으로 입력 gate 차단; 저장 중 일반 키 해제는 버리지 않음 | JVM 비활성 입력 테스트 + 코드 검토 |
| 상태 저장 자동 미리보기와 종료 경쟁 | UI의 외부 스크린샷 캡처 호출 자체 제거, 실제 저장만 수행 | 호출 경로 검색 + 코드 검토; 썸네일은 알파에서 제외 |

## 재현 가능한 검증

SDK 없이 실행할 수 있는 두 프로필 검사(같은 5개 사례, 항상 켜진 CHECK):

```sh
python3 scripts/native_host_tests.py
```

단일 기본 컴파일로 확인하려면:

```sh
g++ -std=c++17 -Wall -Wextra -Werror -pthread \
  app/src/test/cpp/PausedStateAccessTest.cpp -o /tmp/seoul-ds-state-test
/tmp/seoul-ds-state-test
```

실행 관찰:

- 호스트 pthread 테스트 **5/5 PASS**. 이후 최종 하네스에서 `-O0`, `-O2 -DNDEBUG` 각각 같은 5개 사례를 PASS했다. NDEBUG에도 CHECK가 사라지지 않는다.
- 시작/시도 handshake와 pending 확인을 보강한 같은 호스트 테스트 **40회 반복 PASS**.
- UndefinedBehaviorSanitizer 실행 **PASS**.
- AddressSanitizer + UndefinedBehaviorSanitizer, `ASAN_OPTIONS=detect_leaks=0` 실행 **PASS**.
- 기본 LeakSanitizer는 실행 환경의 ptrace 제약으로 실행되지 못했다. **메모리 누수 검증 통과를 의미하지 않는다.**

JVM 저장 정책 테스트는 다음 경로에 9개가 있으며, 별도의 `ui/emulator/input/MelonTouchHandlerTest.kt`에 비활성 입력의 JNI 우회 방지 테스트 1개가 있다. 2026-11-01 전체 Android JVM 실행의 JUnit XML에서 이 10개 모두 실패/오류/건너뜀 없이 PASS했다. 최적화 하네스에서는 변경 없는 JVM 테스트 입력을 Gradle이 UP-TO-DATE로 확인했다. [전체 검증 요약](testing/automated-verification-arm64.json)을 참고한다.

`app/src/test/java/me/magnum/melonds/ui/emulator/savestate/SaveStateOperationCoordinatorTest.kt`

```sh
./gradlew :app:testGitHubProdDebugUnitTest
```

## 남은 한계

- 호스트 동기화 테스트는 실제 에뮬레이터 코어, GPU, 오디오, Android 스케줄러 또는 Galaxy S24 테스트가 아니다.
- 어떤 상용 게임 ROM, BIOS 또는 펌웨어도 테스트 입력으로 받거나 다운로드하지 않았다. 특정 게임 호환성 주장을 하지 않는다.
- SAF 공급자의 파일 교체는 일반 파일시스템과 같지 않다. 저장 상태 쓰기를 원자적 파일 교체/전원 차단 복구 트랜잭션으로 바꾸지는 않았다. 기존 슬롯 덮어쓰기 실패에 대비해 일반 게임 저장과 별도 백업을 유지해야 한다.
- 코어의 일반 저장 flush 정책과 내부 되감기 캡처는 그대로다. 위험한 외부 스크린샷 캡처 경로를 호출하지 않도록 상태 저장 자동 썸네일을 제외했다. 강제 프로세스 종료·저장 공간 부족·외부 문서 공급자 지연은 별도 기기 검증 항목이다.
- 정상 종료 버튼은 비동기 정리를 기다리지만, 운영체제의 강제 프로세스 종료에 대해 작업 완료를 보장하지 않는다.
