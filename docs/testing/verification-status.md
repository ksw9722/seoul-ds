# 검증 현황

이 문서는 검증 층위를 분리하는 인덱스입니다. 최신 자동 검사 결과는 `artifacts/harness/<UTC시간>/report.json`의 실제 실행 증거가 기준이며, 최종 공개 커밋과 대응하는 깨끗한 트리의 재검증 보고서는 배포 묶음에 함께 제공해야 합니다. 아래 구현 검증은 커밋 전 실행이며, 기반 상류 커밋을 수정 APK의 최종 소스 커밋으로 오인하지 않습니다.

| 층위 | 최근 확인 상태 | 완료 증거 |
|---|---|---|
| 권장 최적화 ARM64 전체 자동 하네스 | **PASS · 2026-11-01 17:15~17:18 UTC** | [최신 자동 검증 요약](automated-verification-arm64.json); 원본 final-arm64-optimized |
| 하네스 자체 Python 테스트 | **PASS · 47개** | 최적화 옵션·GNU build-ID 결합·stale APK 거부 회귀 포함 |
| 소스/리소스/출처/비밀 패턴 검사 | **PASS · 12개 게이트** | 최적화 전체 하네스의 source-audit.json |
| C++ 저장 가드 호스트 테스트 | **PASS · 같은 5개 사례 × 2프로필** | -O0, -O2/-DNDEBUG 각각; CHECK가 NDEBUG에도 유지됨 |
| Android/JVM 단위 테스트 | **PASS · 45개, 실패/오류/건너뜀 0** | 앞선 실제 실행 결과와 최적화 실행의 Gradle UP-TO-DATE 검증 |
| Android Lint | **PASS · 번역 baseline 적용** | MissingTranslation 372개 baseline, 경고 164개([번역 부채](lint-debt.md)) |
| 최적화 ARM64 네이티브 링크 | **PASS** | 실제 294개 Ninja 빌드 단계 완료; 구성된 compile DB 400개와 구분 |
| 권장 최적화 ARM64 APK·build-ID 결합 | **PASS** | [패키지 검증](apk-validation-arm64.json), [실제 최적화 증거](optimized-native-proof-arm64.json) |
| 선택적 AOSP Android 에뮬레이터 UI/홈브루 | **NOT RUN · 게스트 부팅 단계 BLOCKED** | [시도·원인·정리 기록](runtime-attempt-aosp.json); 앱 설치/실행 전 플랫폼 watchdog 재시작 |
| 실제 Galaxy S24 UI/저장/성능 | **NOT RUN** | 허가된 S24 실기기·체크리스트 필요 |
| 특정 상용 게임 호환성 | **NOT RUN** | 적법한 사용자 파일·해당 게임 실기기 재현 필요 |
| 소스 공개/원격 CI | **별도 확인 대기** | 실제 GitHub 원격 URL·커밋·체크 ID 필요 |

### 권장 산출물과 개발 백업의 구분

주 산출물은 `seoul-ds-0.1.0-alpha01-arm64-optimized-debug.apk`로, C++ 코어는 RelWithDebInfo 최적화를 사용하지만 **Android 개발 서명·.dev 패키지**다. 실제 최적화 flags·완료된 Ninja graph·최종 APK의 GNU build ID 결합을 확인했다. 전체 Android 하네스도 2026-11-01 17:18:57 UTC에 PASS로 완료되었다. JVM 테스트는 변경 없는 입력에 대해 Gradle이 UP-TO-DATE로 판정했으며, 이전 실제 실행의 45개 통과 결과와 구분해 요약에 기록했다. 최적화 플래그만 켰다고 실행 성능이나 게임 호환성을 주장하지 않는다.

권장 APK는 **34,137,972바이트**, SHA-256은 `7c84fcd709fec40b8a00ccb3115095a49261f46dfcbfa0ee7ca98965c17b57ed`다. 두 emulator 라이브러리가 실제 최적화 그래프의 ELF와 같은 GNU build ID를 가짐을 검사했으며, 모든 네이티브 라이브러리의 ARM64/16 KiB 정렬·ZIP 정렬/CRC·개발 서명·라이선스 자산 일치도 확인했다. 이 검사는 설치나 성능 테스트가 아니다.

앞선 비최적화 개발 프로필의 전체 하네스는 2026-11-01 16:49:28~16:57:14 UTC PASS였고 원본을 `artifacts/harness/final-arm64/`에 그대로 보존했다. 그 APK는37,771,807바이트 / `237613509dd38b6beba752bb8661208faf297f491380ffce444808f2a01448b9`였으며 **개발 백업이지 주 다운로드 선택지가 아니다**. [백업 패키지 검증](apk-validation-arm64-development.json).

더 이른 중간 APK는36,060,628바이트 / `3dc5d6f6b4d951215464c5268b4870f1b3aae7db3cbee618663f40f1227df566`였다. 이미지 정리·API/리소스 수정 전 결과이므로 배포 파일로 사용하지 않는다. 실패/복구와 중간 결과는 아래에 보존한다.

## 알려진 검증 제한

- 사용자의 실제 기기, Android 버전, SoC, 저장소 공급자에 접근하지 않았다.
- 인터넷 ROM 다운로드·독점 BIOS 제공·게임 복제 방지 우회를 수행하지 않는다.
- 에뮬레이터 UI 테스트와 네이티브 코어 게임 실행 테스트는 합성 정책 테스트와 다르다.
- 디버그 APK 빌드는 안정 서명·스토어 정책 준수·성능·저장 무결성 보증이 아니다.

최종 실행 후 요약은 아래에 추가하되, 자동 생성 원본 로그의 경로/커밋을 함께 남긴다. 테스트를 하지 않았다면 이유와 재개 조건을 남긴다.

## 2026-11-01 개발 중 실행 증거

- `artifacts/harness/20261101T155949.584026Z/report.json`: static **PASS**. Python 자체 테스트 17개, 소스 정책 검사 10개, XML 128개 파싱, 소스 경로 3,071개/텍스트 2,856개 고신뢰 패턴 검사, 호스트 네이티브 5개 사례 통과. 당시 작업 트리는 수정 중이므로 최종 커밋 검증이 아니다.
- 새 설정/SAF 순수 정책 JUnit 20개는 독립 Kotlin 컴파일·JUnit 실행에서 PASS 보고됨. 전체 Android Gradle 검증과 구분한다. 로그: 개발 환경 `setup-policy-junit.log`.
- 네이티브 가드 5개 사례의 40회 반복·UBSan 통과; ASan+UBSan은 이 환경에서 지원되지 않는 LeakSanitizer를 끈 설정에서 통과. 상세 조건은 [저장 안전성](../save-safety-ko.md).
- Android 전체 빌드/Lint/JUnit, 선택적 AOSP 에뮬레이터 UI 검증은 별도 진행 중이며 이 기록으로 통과를 가정하지 않는다. 실제 S24/상용 게임은 계속 **NOT RUN**.

### 전체 Android 첫 시도

첫 통합 Gradle 실행은 Kotlin/Java 컴파일 단계 이후 daemon이 사라져 **FAIL**(환경 메모리 압박 추정)로 끝났다. 테스트/Lint/APK 전체 통과로 기록하지 않는다. 재시도는 작업을 분리하고 Gradle worker 1개·Kotlin in-process·네이티브 병렬 수 제한을 사용한다. 최종 결과는 새 실행 로그로 교체/추가하며 실패 이력은 보존한다.

### 라이선스·하네스 추가 확인

- 실제 `gitHubProdDebugRuntimeClasspath`: 외부 모듈214개, 실제 바이너리아티팩트161개 해시, 고지104개/고유원문13개 수집. POM/상속 라이선스 누락0. 이 메타데이터 감사는 법률 인증이 아니며 PCAP 광고 조항 위험은 별도로 처리한다.
- 이 중간 실행에서 하네스 자체 테스트는 25개 PASS로 확장했다: 중단된 Android 실행의 부분 PASS 방지, POM 상속/중첩AAR 고지 추출, dirty source 배포 거부, 같은 커밋의 결정적 소스아카이브 재생성 회귀 테스트 포함.

### Android JVM 테스트 재시도

2026-11-01 분리 실행한 `:app:testGitHubProdDebugUnitTest`가 **BUILD SUCCESSFUL**로 완료되었다(3분33초, `unit-final.log`). 이는 JVM 테스트 단계의 완료이며 Android Lint·APK·UI/게임 검증으로 확대하지 않는다. JUnit XML을 직접 집계해 45개, 실패0/오류0/건너뜀0을 확인했다(원작 버전13, 시작정책14, SAF6, 저장조정9, 터치1, 업데이트2). 최종 커밋 반영 여부는 배포 직전 다시 확인한다.

### 직접 작성한 홈브루 fixture

2026-11-01 `tests/homebrew/`의 새 GPL-3.0-only 소스를 고정 NDK로 빌드하고 8개 파일 구조/변조 검사를 통과했다. 생성물은 무시된 `artifacts/homebrew/`에만 있으며 반복 빌드의 ROM/manifest 해시가 같았다. ROM SHA-256: `19dba2f22ef982c36dc8a6e1a71c7ec10ce4d884865778fef8b0bfb242284d26`. 이 기록 시점에서 실제 실행은 **NOT RUN**이며 실행 결과를 별도로 추가해야 한다. 지원 검증 범위는 듀얼 단색 화면·A/B·상태 복원뿐이고 터치·소리·게임 내부 SRAM/상용 게임 호환성의 증거가 아니다.

### ARM64 네이티브 빌드 메모리 실패와 재개

두 번째 APK 시도는 대형 Teakra C++ 소스와 Gradle JVM이 동시에 메모리를 사용하는 구간에서 daemon이 사라져 **FAIL**로 종료되었다(네이티브400개 중105개 객체 단계, 호스트 메모리 압박 관찰). Kotlin/JVM 테스트 통과를 APK 빌드 통과로 바꾸지 않는다. 복구는 [저메모리 빌드 경로](../building.md)를 따라 같은 CMake 그래프를 Gradle JVM 없이 Ninja `-j1`로 빌드한 뒤 패키징을 재개한다. 이 실패 기록 시점에서는 최종 APK/링크 결과가 대기 중이었으며, 이후 복구 결과는 다음 항목과 위의 최신 표를 참조한다.

### ARM64 네이티브 복구·PCAP 제외 확인

Standalone Ninja `-j1` 복구는 남은186개 단계와 두 네이티브 라이브러리 링크까지 **PASS**했다. 실제 compile graph400개·Ninja 의존성166,497줄·두 unstripped ELF 심볼에서 PCAP 단위/헤더/심볼0을 확인했다. [해시·재현 명령](native-pcap-audit.md). APK 패키징은 그 다음 단계이며 이 결과를 설치/실행 성공으로 확대하지 않는다.

### 초기 Android Lint 결과와 범위 제한

전체 Lint 첫 결과는379개 오류였으며 PASS가 아니다. 이 중372개는 `MissingTranslation`이다. 195개는 새 한국어 로케일만의 미번역,170개는 한국어와 기존 로케일이 섞인 미번역,7개는 기존 로케일만의 미번역이다. 전부 상류에서 물려받은 오류라고 주장하지 않는다. 별도 검토한 **번역 항목만 포함하는 baseline**으로 관리하고, API/실행 안전성·서식/복수형 오류는 코드/리소스를 고친다. 최종 Lint 결과는 "검토된 localization baseline 적용 후 통과"라고 표시해야 하며 **경고/미완성 번역이0개**라고 말하지 않는다. baseline의 ID·개수 제한과 근거는 [번역 부채 문서](lint-debt.md)와 별도 회귀 검사에 남긴다.

### 최적화 네이티브 프로필·실제 APK 결합

2026-11-01 RelWithDebInfo 그래프의 순차 네이티브 빌드가 294개 Ninja 단계까지 완료되었다. 컴파일 데이터베이스에는 **400개의 구성된 단위**가 있지만 실제 빌드 단계 수와 같은 의미가 아니다. 그중 C/C++ 399개 모두 유효 옵션이 `-O2`·`-g`·`-DNDEBUG`였고, 나머지 하나는 어셈블리다. 하네스의 47개 Python 회귀 테스트와 동일한 5개 C++ 사례의 비최적화/최적화 두 프로필 검사를 통과했다.

`optimized-native-proof-arm64.json`은 완료된 Ninja 타깃, 실제 컴파일러 의존성 166,617줄의 PCAP 제외, 두 실제 ELF의 PCAP 심볼 부재를 확인했다. 또한 APK의 core/frontend GNU build ID가 해당 그래프의 출력과 각각 일치했다. 요청 플래그만 확인하거나 이전 비최적화 APK를 새 결과로 취급하지 않았다. 최적화 전체 하네스도 이후 PASS로 완료되었고 위의 최신 요약에 연결했다. 이 실행의 Lint는 번역 baseline 372개와 경고 164개를 기록했다(이전 개발 프로필의 경고는 159개).

## 선택적 AOSP 실행 시도 결과 · 앱 런타임 NOT RUN

2026-11-01 별도 **테스트 전용 x86_64 최적화 APK**를 빌드하고 패키지/네이티브 build-ID 일치를 확인했다. 크기 34,367,349바이트, SHA-256 `5931d5aef98df5c087a4f07b8fab99e343963c57da530356010b754916b43f78`이다. 이 파일은 권장 ARM64 산출물과 다르며 사용자 다운로드 선택지가 아니다. [x86_64 패키지 검증](apk-validation-x86_64-test-only.json), [실제 빌드 증거](optimized-native-proof-x86_64-test-only.json).

그러나 AOSP API 36 x86_64 시스템 이미지(revision 2), Android Emulator 37.2.13.0을 하드웨어 가속 없이 부팅하는 단계에서 막혔다. 첫 시도는 17:31:35 UTC에 시작해 17:40:55 UTC 호스트 실행 세션 중단으로 끝났다(관찰 루프에 보낸 Ctrl-C가 세션 전체를 종료; 게스트 실패로 단정하지 않음). 복구 셸은 17:42:21 UTC에 시작했고 에뮬레이터는 약 17:43:06~17:52:16 UTC 동안 실행했으며, 게스트 watchdog이 메인 스레드 79초 정지를 보고한 뒤 약 452~459초 guest uptime에 진단/zygote 종료와 플랫폼 서비스 재시작이 발생했다. 당시 blocked stack은 `ConnectivityService.systemReadyInternal:4190`이었다. SystemUI/PermissionController는 `DeadSystemException`을 보고했고 `sys.boot_completed`는 완료되지 않았다. 더 깊은 플랫폼 원인을 확정하지 않으며, 이는 앱이 실행되다 실패한 결과가 아니다.

**Seoul DS APK 설치·앱 시작·UI smoke·직접 만든 홈브루 실행 모두 NOT RUN**이다. 작업 소유 에뮬레이터를 명시적으로 종료했고 남은 해당 프로세스/ADB 기기가 없음을 확인했다. 종료 뒤 기록된 emulator wait 139도 앱 충돌로 분류하지 않는다. 정확한 범위와 원본 증거 해시는 [AOSP 시도 기록](runtime-attempt-aosp.json)에 남겼다.

재개하려면 정상 부팅되는 가속 지원 테스트 호스트 또는 명시적으로 승인된 기기를 준비하고, 정확한 ABI APK를 설치한 뒤 UI와 홈브루 실행을 각각 검사한다. 이 환경 제약은 자동 빌드·정적/JVM/호스트 검사 통과를 취소하지 않지만, **그 통과를 설치·게임 실행 검증으로 확대할 근거도 제공하지 않는다.** 실제 S24와 특정 상용 게임의 결과는 계속 NOT RUN이다.
