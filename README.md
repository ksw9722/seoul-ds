# Seoul DS · 서울 DS

**한국어 시작 안내와 설정 점검을 더한 Android DS 에뮬레이터.**
[melonDS Android 2.0.1](https://github.com/rafaelvcaetano/melonDS-android/tree/2.0.1)을 기반으로 한 독립적인 GPL 오픈소스 포크입니다. 원작 개발자들의 에뮬레이션 코어·듀얼 화면·터치·오디오·저장 기능을 계승합니다. 원작이나 Nintendo의 공식 앱이 아닙니다.

> **검증 범위:** Galaxy S24와 특정 상용 게임의 실기기 실행은 아직 검증하지 않았습니다. 빌드 성공·정적 검사·단위 테스트를 게임 호환성 또는 저장 안정성의 실기기 검증으로 해석하지 마세요. 최신 검증 기록은 [검증 현황](docs/testing/verification-status.md)과 실행별 `artifacts/harness/` 보고서에 구분합니다.

개인 사용용 **ARM64 네이티브 최적화 APK와 전체 자동 하네스가 통과**했습니다. JVM 테스트 45개, Python 테스트 47개, 두 프로필의 네이티브 동기화 검사와 실제 최적화 그래프·패키지 일치를 확인했습니다. Lint는 번역 누락 372개 기준선과 경고 164개를 남긴 상태로 통과했습니다. 추가 AOSP 실행 검사는 게스트 OS 부팅 실패로 앱 설치 전 차단되어 UI/게임 실행은 미검증입니다. 실기기·최종 공개 상태는 [검증 현황](docs/testing/verification-status.md)에서 별도로 구분합니다.

## 개발 중: 1–5배속 및 한 기기 2P

새 변경은 아직 APK로 빌드·배포하거나 실기기로 검증하지 않은 개발 코드입니다.

- 속도 버튼을 누를 때마다 **1× → 2× → 3× → 4× → 5× → 1×**로 전환합니다. 현재 배속을 표시하며 실제 속도는 기기와 게임 성능에 따라 목표에 못 미칠 수 있습니다.
- 실험적 2P는 **한 전화에서 두 DS를 실행하고 1P/2P 화면을 전환**합니다. 같은 ROM의 독립적인 두 번째 게임 내부 세이브를 사용합니다. 다른 전화와 연결하는 기능은 아닙니다.
- 2P는 DS/소프트웨어 렌더러/1배속으로 제한합니다. 두 번째 세이브 가져오기·계속하기·새로 시작하기와 내보내기, 시작 전 1P 백업을 제공합니다.
- **포켓몬 교환 성공은 미검증**입니다. [2P 안전 안내와 실기기 검증표](docs/two-player-experimental-ko.md)를 먼저 확인하세요.

## 이 포크에서 바뀌는 것

- 독립 설치 ID `io.github.seoulds.emulator` (개발 APK는 `.dev`), Seoul DS 이름과 자체 아이콘.
- 한국어 우선 시작 가이드: 합법적으로 보유한 로컬 파일, Android 폴더 권한, 저장 데이터 보호, DS 직접 부팅 안내.
- 설정 상태를 확인하고 기존 ROM/에뮬레이터 설정으로 이동하는 안내 화면.
- [AI-DLC 요구사항 → 설계 → 검증 → 배포](docs/ai-dlc/README.md)와 반복 실행 가능한 [검증 하네스](docs/testing/harness.md).
- 취소·권한 오류에 기존 폴더 선택을 보존하는 SAF 처리, [저장/불러오기 동시성 안전성](docs/save-safety-ko.md) 개선.
- 원작 자동 릴리스/Play Store 업로드를 제거한 읽기 전용 검증 CI.

**알파 제한:** 한국어는 새 시작 안내·주요 탐색을 중심으로 제공하며 일부 원작 고급 설정은 영어로 표시됩니다([번역 범위·Lint 부채](docs/testing/lint-debt.md)). 상태 저장 슬롯의 새 자동 미리보기 이미지는 종료 경쟁 조건을 피하기 위해 생성하지 않습니다. 저장·불러오기는 유지하며 자리 표시자를 사용합니다.

**포함하지 않는 것:** 상용 게임 ROM, Nintendo BIOS·펌웨어, 게임 표지·스크린샷, 불법 다운로드 경로, 복제 방지 우회 패치. 일반 DS 직접 부팅은 원작의 FreeBIOS/생성 펌웨어를 이용하며, 원본 펌웨어 부팅이나 DSi는 별도 조건이 있습니다. 자세한 사용법은 [한국어 시작 안내](docs/quickstart-ko.md)를 읽어 주세요.

공개 소스의 이력·원본 체크섬·포함 방식은 [공개 스냅샷 안내](docs/published-snapshot.md)를 확인하세요.

## 빌드

Java 21, Android SDK 36, NDK `28.0.13004108`, CMake `3.22.1`이 필요합니다. Gradle은 저장소의 9.1.0 Wrapper를 사용합니다.

```bash
# 공개 저장소 또는 소스 사본을 가져온 뒤
# 이 공개 스냅샷은 하위 모듈 소스를 일반 파일로 포함합니다.
# 별도 submodule 다운로드가 필요하지 않습니다.
python3 scripts/harness.py --mode static

# Android SDK 약관을 직접 확인·동의하고 필요한 도구를 설치한 환경에서만
export ANDROID_HOME=/path/to/android-sdk
export ANDROID_SDK_LICENSE_ACCEPTED=true
python3 scripts/harness.py --mode android --abi arm64-v8a --optimized-native
```

Android 모드는 정적 검사 → JVM 단위 테스트 → Android Lint → ARM64 APK 빌드 → 실제 네이티브 최적화/패키지 증거를 각각 기록합니다. 권장 `--optimized-native`는 C++ 코어를 RelWithDebInfo(-O2/-O3, NDEBUG)로 빌드하지만 APK는 여전히 **개발 서명·.dev 패키지**입니다. 옵션을 생략한 비최적화 빌드는 개발 진단용이며 주 배포 선택지가 아닙니다. 결과는 `artifacts/harness/<UTC시간>/report.json`, 명령별 로그와 `summary.md`에 남습니다. APK는 일반적으로 `app/build/outputs/apk/gitHubProd/debug/app-gitHub-prod-debug.apk`에 생성됩니다. **실제 생성 여부와 SHA-256은 보고서가 기준**입니다. 기본 Gradle ABI 목록은 원작과 같고, `-PseoulDsAbis=arm64-v8a`로 S24 대상 빌드를 제한할 수 있습니다.

오프라인 소스 검사에는 Python 3 표준 라이브러리와 Git이 필요하며, static 하네스의 네이티브 동기화 테스트에는 C++17 `g++`도 필요합니다. SDK가 없거나 약관 동의가 명시되지 않으면 Android 단계는 `BLOCKED`이며, 성공으로 처리하지 않습니다. 세부 설치·재현 절차는 [빌드 가이드](docs/building.md)를 참고하세요.

## 안전한 사용·기여

- ROM/BIOS 파일이나 개인정보를 이슈에 올리지 마세요. 재현 절차, 기기 모델·Android 버전, 익명화된 오류만 공유하세요.
- 중요한 진행도는 **게임 내부 저장**을 사용하고 저장 폴더를 별도 백업하세요. 상태 저장은 보조 기능이며 버전 간 호환을 보장하지 않습니다.
- 디버그 서명은 개발 확인용입니다. 공개 정식 배포 키와 업데이트 정책을 확정하기 전 이를 안정 릴리스로 취급하지 마세요.
- [직접 만든 테스트 홈브루 소스](tests/homebrew/README.md), [S24 실기기 검증표](docs/testing/s24-device-checklist.md), [개인정보 안내](docs/privacy-ko.md), [배포 점검](docs/releasing.md)을 확인하세요.

## 저작권·소스

이 포크는 GPL-3.0로 배포합니다. [LICENSE](LICENSE), 원작 파일의 저작권 표시, [서드파티 고지](docs/third-party-notices.md)를 유지합니다. 정확한 기반 버전과 하위 모듈 커밋은 [upstream-lock.json](docs/upstream-lock.json)에 고정했습니다. 수정 APK를 배포할 때에는 **해당 바이너리를 만든 수정 소스·하위 모듈·빌드 스크립트**를 함께 제공해야 합니다. `scripts/package_source.py`는 깨끗하고 커밋된 소스로 재귀적 소스 묶음과 해시를 생성합니다.

[원작 README(텍스트 보존본)](README.upstream.md) · [설계 결정](docs/ai-dlc/design.md) · [변경 기록](docs/CHANGELOG.md)

## GitHub alpha APK 배포

Actions의 **Seoul DS alpha APK prerelease**를 기본 브랜치에서 수동 실행하면 검사 통과 후 개발용 ARM64 APK와 전체 대응 소스·체크섬·고지를 공개 prerelease로 배포합니다. SDK/NDK 약관 동의 입력이 필요합니다. `alpha-*` 태그 방식은 저장소 변수 `ANDROID_SDK_LICENSE_ACCEPTED=true`가 기록된 경우에만 실행됩니다.

이 APK는 매 실행마다 임시 debug 키로 서명하며 정식 업데이트용 서명이 아닙니다. 이전 빌드 위에 설치되지 않을 수 있으므로 삭제 전 세이브를 백업하세요. **Galaxy S24 실기기/게임 실행은 미검증**입니다. [배포 절차와 제한](docs/releasing.md#github-actions-alpha-prerelease)을 확인하세요.
