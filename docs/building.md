# 빌드와 재현

## 고정 도구

| 항목 | 값 |
|---|---|
| JDK | 21 |
| Gradle Wrapper | 9.1.0, Wrapper에 배포 ZIP SHA-256 고정 |
| Android compile/target SDK | 36 |
| 최소 Android SDK | 24 (Android 7.0) |
| NDK | 28.0.13004108 |
| CMake | 3.22.1 |
| 주요 APK ABI | arm64-v8a |

공식 [Android command-line tools](https://developer.android.com/studio#command-line-tools-only)를 사용하세요. [Android SDK 약관](https://developer.android.com/studio/terms)을 확인하고 본인이 동의한 경우에만 설치·사용하세요. 이 저장소의 하네스는 로컬 SDK 약관에 자동 동의하거나 도구를 내려받지 않습니다. Gradle 최초 실행은 공식 배포 ZIP/의존성을 내려받기 때문에 네트워크가 필요합니다.

```bash
export JAVA_HOME=/path/to/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
export ANDROID_HOME=/path/to/android-sdk
# 홈 디렉터리가 읽기 전용인 환경에서는 쓰기 가능한 별도 경로를 사용합니다.
export ANDROID_USER_HOME=/writable/path/android-user-home
export GRADLE_USER_HOME=/writable/path/gradle-user-home

# 공식 sdkmanager가 아래 선택한 구성요소에 제시하는 약관을 직접 검토/동의합니다.
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --install \
  'platforms;android-36' 'build-tools;36.0.0' \
  'ndk;28.0.13004108' 'cmake;3.22.1'
export ANDROID_SDK_LICENSE_ACCEPTED=true

git submodule update --init --recursive
python3 scripts/harness.py --mode android --abi arm64-v8a --optimized-native
```

완전한 `seoul-ds-<commit>-source.tar.gz`를 풀었다면 하위 모듈 소스가 이미 포함되어 있으므로 Git metadata가 없는 상태에서 `git submodule update`를 실행할 필요가 없습니다. GitHub의 자동 Source code ZIP은 별개이며 하위 모듈이 빠질 수 있습니다. 소스 묶음에서는 `SOURCE_MANIFEST.json`으로 원본 해시를 검증할 수 있습니다. APK의 바이트 단위 재현성(예: 별도 생성되는 디버그 서명키)까지 보장하는 것은 아닙니다.

`ANDROID_SDK_LICENSE_ACCEPTED=true`는 이미 한 동의의 명시적 기록이며 약관을 대신하지 않습니다. CI는 저장소 관리자가 동명의 **Repository variable**을 `true`로 설정한 경우에만 Android 작업을 실행합니다. CI에 설치되는 SDK 구성요소와 라이선스 동의 단계는 `.github/workflows/verify.yml`에 공개되어 있습니다. 값이 없으면 해당 작업은 **skipped**이며 Android 검사 통과가 아닙니다.

## 이번 실행의 정확한 도구 출처

프로젝트의 이식 가능한 요구사항은 **JDK 21**이며 CI도 Temurin 21을 선택한다. 향후 CI가 선택하는 패치 버전은 달라질 수 있다. 이번 로컬 최적화 ARM64 빌드에서 실제 사용한 버전은 다음과 같으며, [구조화된 도구 출처·아카이브 SHA-256](build-toolchain-2026-11-01.json)에 기록했다.

- Linux x86_64용 Eclipse Temurin **21.0.13+9-LTS JDK**, Java 배포 날짜 2026-10-20. 설치된 `release` 정보와 공식 release metadata 및 내려받은 파일의 SHA-256을 대조했다.
- Android command-line tools **22.0** (`commandlinetools-linux-15859902_latest.zip`), 설치 정보와 다운로드 해시 기록.
- Android SDK Platform 36 **revision 2 / extension level 17**, Build Tools 36.0.0.
- NDK 28.0.13004108(r28), CMake 3.22.1, SHA-256이 고정된 Gradle Wrapper 9.1.0.

이는 **실제 실행 도구의 출처 기록**이지 모든 호스트를 그 패치 버전에 묶는 추가 요구사항이나 APK 바이트 재현성 보증은 아니다. 도구 아카이브·로컬 경로·서명키는 소스 배포에 넣지 않는다. 다른 도구로 검증할 때에는 해당 실행의 실제 버전을 새로 기록한다.

## 권장 네이티브 최적화 프로필

`--optimized-native`는 모든 Android Gradle 단계에 `-PseoulDsOptimizeNative=true`를 전달한다. CMake cache의 실제 값이 `SEOUL_DS_OPTIMIZED_NATIVE=ON`/`CMAKE_BUILD_TYPE=RelWithDebInfo`인지, 유효 컴파일 옵션이 `-O2` 또는 `-O3`·`-g`·`-DNDEBUG`인지 검증한다. 단순 요청 플래그를 최적화 성공 증거로 사용하지 않는다.

Android 빌드 variant는 계속 Debug이므로 디렉터리는 `.cxx/Debug/`일 수 있고, 설치 ID `.dev`·개발 서명도 바뀌지 않는다. 정식 배포 키나 새 flavor를 추가하지 않는다. 최적화는 실행 성능을 보장하거나 S24 벤치마크를 대신하지 않는다.

빌드 후 하네스의 `optimized-native-proof` 단계는 Ninja 실제 의존성/업데이트 상태와 PCAP 제외를 확인하고, **APK의 두 emulator .so GNU build ID를 해당 최적화 그래프의 실제 비스트립 ELF와 대조**한다. 이전 비최적화 APK 또는 다른 graph가 섞이면 실패한다. 여러 최적화 그래프가 남으면 추측하지 않으며 `--native-build-dir`로 실제 빌드 경로를 지정해야 한다.

```bash
python3 scripts/harness.py --mode android --abi arm64-v8a --optimized-native \
  --native-build-dir app/.cxx/Debug/ACTUAL_GENERATED_HASH/arm64-v8a
# 검증만 따로 수행할 때
python3 scripts/validate_optimized_native.py \
  --apk app/build/outputs/apk/gitHubProd/debug/app-gitHub-prod-debug.apk \
  --abi arm64-v8a --native-dir app/.cxx/Debug/ACTUAL_GENERATED_HASH/arm64-v8a \
  --json artifacts/optimized-native-proof.json
```

권장 배포명은 `seoul-ds-0.1.0-alpha01-arm64-optimized-debug.apk`다. 비최적화 APK는 개발 백업으로만 구분하고 사용자에게 동등한 다운로드 선택지로 제시하지 않는다.

## 개별 실행

```bash
python3 -m unittest discover -s scripts/tests -v
python3 scripts/audit_source.py
python3 scripts/native_host_tests.py  # g++17/pthreads, Android가 아님
./gradlew --no-daemon -PseoulDsAbis=arm64-v8a -PseoulDsOptimizeNative=true :app:testGitHubProdDebugUnitTest
./gradlew --no-daemon -PseoulDsAbis=arm64-v8a -PseoulDsOptimizeNative=true :app:lintGitHubProdDebug
./gradlew --no-daemon -PseoulDsAbis=arm64-v8a -PseoulDsOptimizeNative=true :app:assembleGitHubProdDebug
```

APK 생성 후 패키지를 별도로 검증할 수도 있습니다. 설치하거나 ROM을 실행하지 않습니다.

```bash
python3 scripts/validate_apk.py \
  --apk app/build/outputs/apk/gitHubProd/debug/app-gitHub-prod-debug.apk \
  --abi arm64-v8a --json artifacts/apk-validation.json
```

디버그 결과 경로: `app/build/outputs/apk/gitHubProd/debug/`. Android SDK의 `apksigner verify --verbose`와 `aapt dump badging` 또는 `apkanalyzer`로 패키지 ID, SDK, ABI와 서명을 확인하세요. 디버그 키는 로컬 생성이며 안정 업데이트용 서명키가 아닙니다. `local.properties`, 키, 캐시, 개인 ROM/세이브를 Git에 넣지 마세요.

## 실패 분류

- **BLOCKED:** SDK·JDK 부재, 미동의, 쓰기 불가 도구 경로 등 실행 전제 미충족.
- **FAIL:** 컴파일·테스트·Lint·소스 정책 실패, 타임아웃. 로그를 읽고 원인을 수정한 뒤 새 실행 디렉터리에서 재검사합니다.
- **NOT RUN:** 선택한 범위 밖 또는 실제 기기/테스트 파일을 사용할 수 없어 미실행.
- **PASS:** 해당 명령의 종료 코드 및 산출물이 확인됨. 다음 단계나 기기 호환성까지 확장해 해석하지 않습니다.

Gradle daemon을 계속 재시작하거나 캐시 전체 삭제로 문제를 숨기지 마세요. 네트워크·메모리·빌드 오류를 구분하고, 공식 저장소 의존성 경로를 유지하세요. 프록시 인증정보·토큰이 있는 로그는 공개 전 제거해야 합니다.

## 메모리가 적은 빌드 호스트의 복구 경로

이번 개발 환경에서 Gradle JVM·Kotlin/분석기·템플릿이 큰 네이티브 C++ 컴파일이 겹칠 때 daemon이 종료되는 실패가 관찰되었다. 앱 코드 컴파일 오류와 구분하고, 실패한 실행을 성공으로 덮어쓰지 않는다. 우선 다른 에뮬레이터/빌드 작업을 멈추고 worker1·Kotlin in-process를 사용한다. 루트 CMake는 네이티브 compile/link pool을 각각1로 제한한다.

그래도 메모리가 부족하면 **동일하게 생성된 CMake/Ninja 그래프**의 네이티브 빌드를 Gradle JVM이 없는 동안 순차 수행할 수 있다. 임의로 소스/컴파일 옵션을 바꾸는 우회가 아니다. SDK/NDK는 앞서 설치·동의한 고정 도구를 사용한다.

```bash
# 1. Gradle가 원래 프로젝트의 네이티브 그래프를 생성하게 한 뒤 종료한다.
./gradlew --no-daemon --max-workers=1 -Pkotlin.compiler.execution.strategy=in-process \
  -PseoulDsAbis=arm64-v8a -PseoulDsOptimizeNative=true ':app:configureCMakeDebug[arm64-v8a]'

# 2. 방금 생성된 arm64-v8a 그래프를 찾는다. 해시 폴더는 환경마다 달라진다.
find app/.cxx/Debug -path '*/arm64-v8a/build.ninja' -print
# 위 결과에서 정확히 방금 생성된 그래프의 부모 디렉터리를 지정한다.
NATIVE_DIR=app/.cxx/Debug/ACTUAL_GENERATED_HASH/arm64-v8a
"$ANDROID_HOME/cmake/3.22.1/bin/ninja" -C "$NATIVE_DIR" -j1 melonDS-android-frontend

# 3. 같은 ABI/설정으로 Gradle 패키징을 재개한다.
./gradlew --no-daemon --max-workers=1 -Pkotlin.compiler.execution.strategy=in-process \
  -PseoulDsAbis=arm64-v8a -PseoulDsOptimizeNative=true :app:assembleGitHubProdDebug
python3 scripts/validate_apk.py \
  --apk app/build/outputs/apk/gitHubProd/debug/app-gitHub-prod-debug.apk --abi arm64-v8a
```

오래된 다른 ABI/설정의 그래프를 선택하지 마세요. 최신 CMake 설정과 submodule pin, compiler command를 검토하고 동일한 파일을 사용해야 합니다. 이 분리 빌드만으로 단위 테스트/Lint를 생략하지 않습니다. 최종 APK 생성·패키지 검증이 완료되기 전까지는 복구 중이며 통과가 아닙니다.
