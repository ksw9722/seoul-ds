# 검증 하네스

```bash
python3 scripts/harness.py --mode static
python3 scripts/harness.py --mode android --abi arm64-v8a --optimized-native
```

| 검사 | 범위 | 증거 |
|---|---|---|
| harness-self-tests | 비밀 패턴을 값 없이 보고, 위험 경로·FreeBIOS 해시 예외, 상태 분류, 소스 패키징 경로 정책 | Python unittest 로그 |
| source-audit | 버전/하위 모듈 pin, XML 문법, 독립 ID, DS 부팅 기본값, 금지 배포 경로·일부 고신뢰 비밀 패턴, CI 권한/정책 | source-audit.json |
| native-host-tests | 같은 5개 동기화 사례를 -O0와 -O2/-DNDEBUG에서 각각 실행, 항상 켜진 CHECK 사용 | 호스트 g++17 두 프로필 로그(서로 다른 10개 사례라는 뜻 아님) |
| local-mp-host-tests | 실제 LocalMP의 합성 패킷 전달·타임스탬프·자기 패킷 제외·FIFO 순환·병렬 응답·종료/재접속을 -O0 및 -O2/-DNDEBUG에서 검사; Android/게임 실행 아님 | 호스트 g++17 로그 |
| android-semaphore-host-tests | Android 소스의 실제 pthread 세마포어 함수 추출·호스트 실행: 절대 시각 정규화, 양수 timeout, 잠금 해제, 신호 및 초기화; Android 실행 아님 | 호스트 g++17 로그 |
| save-manager-host-tests | 실제 SaveManager와 합성 파일 오류: 열기/쓰기/flush/닫기 실패 유지 및 재시도, 부분 변경, 메모리 내보내기 | 호스트 g++17 로그 |
| second-player-session-host-tests | 실제 P2 스레드 루프/중단 함수 추출 + 가짜 core/EGL: 1000회 재개/정지, 초기화 실패, 예외 시 렌더 자원 보존, 정상 종료 | 호스트 g++17 로그; 실제 EGL/게임 아님 |
| jvm-unit-tests | 원작 버전 비교 + 새 시작/저장 정책의 Android JVM 테스트 | Gradle/JUnit XML·HTML |
| android-lint | Android 정적 Lint | Gradle·Lint 보고서 |
| debug-apk | 선택 ABI의 Debug APK 생성 | Gradle 로그·APK 크기·SHA-256 |
| optimized-native-proof | 실제 최적화 cache/유효 옵션·Ninja up-to-date·PCAP 제외 + APK/실제 ELF GNU build ID 일치 | optimized-native-proof.json; 요청 플래그만으로 PASS 불가 |
| apk-validation | 공식 aapt/apksigner 패키지 ID·SDK·서명, ELF ABI·16KiB LOAD 정렬/네이티브 라이브러리, zipalign·ZIP CRC, 라이선스 바이트 일치 | apk-validation.json |
| s24-and-game-runtime | 자동 실행하지 않음 | 별도 실기기 체크리스트 |

각 실행은 새 UTC 타임스탬프 디렉터리를 만들며 이전 결과를 덮어쓰지 않습니다. 명령, 종료 코드, 실행 시간, Git HEAD, 작업 트리 변경, 하위 모듈 상태를 기록합니다. 시작 전에 모든 예정 검사를 PENDING으로 기록하고 진행 중에는 RUNNING이며 완료 시간은 기록하지 않습니다. 프로세스가 중간에 끊긴 부분 결과를 PASS로 오인하지 않도록 최종 종료 시에만 완료 상태를 씁니다. `--output`은 새 디렉터리만 허용합니다. `--timeout`은 명령별 상한이며 초과 시 FAIL입니다. 타임아웃을 성공으로 바꾸거나 미실행 결과를 PASS로 표시하지 않습니다.

**전체 PASS의 의미는 선택한 범위의 자동 검사가 성공했다는 뜻뿐**입니다. static 모드의 Android 검사는 NOT RUN입니다. 실제 기기 검사는 두 모드 모두 NOT RUN이며 빌드 성공으로 대체하지 않습니다. 소스 검사는 파일 이름/일부 패턴 기반으로 보수적으로 검사하며 숨겨진 비밀, 모든 저작권 문제, 모든 의존성 라이선스를 증명하지 않습니다.

## 가짜 데이터 원칙

하네스 테스트는 합성 문자열·임시 텍스트 파일·격리된 C++ 상태 객체를 사용합니다. Nintendo 게임/BIOS, 상용 게임 세이브, 인터넷에서 받은 ROM은 사용하지 않습니다. 홈브루 실행 테스트는 별도 승인·명확한 출처/라이선스가 있는 파일로 추가해야 합니다.

## 실패 대응

1. `report.json`에서 FAIL/BLOCKED인 검사를 확인합니다.
2. 대응 로그의 최초 원인을 확인하고 소스/도구/환경 오류를 구분합니다.
3. 수정 후 같은 커밋 상태를 기록하는 새 실행을 수행합니다.
4. 공개 보고서는 최종 커밋과 일치해야 합니다. 마지막 검사 이후 변경이 있으면 영향 범위를 다시 검사합니다.
5. 원본 로그는 무시된 `artifacts/`에 두고, 필요한 익명화 요약만 커밋합니다. 서명키·토큰·개인 문서 경로는 공개하지 않습니다.

## 선택적 원본 홈브루 검사

`tests/homebrew/`에는 이 포크를 위해 새로 작성한 GPL-3.0-only ARM9/ARM7 테스트 소스가 있다. 상용 ROM/BIOS/부팅 로고·외부 홈브루 코드를 복사하지 않으며, 결과 `.nds`는 무시된 `artifacts/homebrew/`에만 생성한다. SDK/NDK 설치·동의는 먼저 완료되어 있어야 한다.

```bash
ANDROID_NDK_HOME="$ANDROID_HOME/ndk/28.0.13004108" bash tests/homebrew/build.sh
python3 -B tests/homebrew/test_format.py
```

8개 형식/변조 테스트는 헤더/배너 CRC, 로고 0 채움, 주소 경계/영역 중첩, 소스 해시를 검사한다. 이는 `.nds` 파일이 실행되었다는 의미가 아니다. 선택적 실제 실행은 양 화면 색상, A/B 입력, 에뮬레이터 상태 복원을 관찰하기 위한 것이며 **터치, 오디오, 게임 내부 SRAM 저장은 검증하지 않는다.** 오프라인 static CI는 NDK나 생성 ROM을 요구하지 않으므로 이 단계는 자동 포함하지 않는다.

## 선택적 AOSP 에뮬레이터 UI 검사

`android_ui_smoke.py`는 **폐기 가능한 AOSP Android 에뮬레이터 전용**이다. 실제 전화에서는 실행하지 않는다. 명시한 `emulator-*` serial과 `ro.kernel.qemu=1`을 모두 확인하며, 테스트용 앱 데이터를 지우고 로그 버퍼를 비운다. 개인 파일·계정·중요한 진행도가 없는 에뮬레이터에서만 사용한다.

별도로 빌드한 x86_64 Debug APK를 해당 에뮬레이터에 설치한 뒤 실행한다. ABI별 빌드 결과는 같은 기본 APK 경로를 사용할 수 있으므로 **권장 ARM64 APK와 해시를 먼저 별도 보존**하고 서로 덮어쓰지 않는다. 메모리가 적은 호스트에서는 빌드와 에뮬레이터 실행을 동시에 하지 않는다.

```bash
# SERIAL은 현재 작업에서 만든 테스트용 에뮬레이터의 실제 serial로 지정한다.
SERIAL=emulator-5554
python3 scripts/android_ui_smoke.py \
  --adb "$ANDROID_HOME/platform-tools/adb" --serial "$SERIAL" \
  --allow-clear-test-data --output artifacts/ui-smoke/NEW_RUN_DIRECTORY
```

이 검사는 첫 안내·뒤로/재시작·폴더 선택 취소·회전·오프라인 라이선스·명시적 완료/메뉴 재진입과 충돌 버퍼를 확인한다. 안내 접근 가능성은 전체 UI 적합성 인증이 아니고, **ROM 실행·터치/소리·게임 세이브·S24 호환성은 검사하지 않는다.** 화면/접근성 XML과 JSON 결과를 보존하며, 직접 작성한 홈브루 실행 결과는 이 UI 검사와 별도로 기록한다. 실행하지 않은 상태를 PASS로 해석하지 않는다.
