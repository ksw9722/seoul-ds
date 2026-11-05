# Lint 기준선: 번역 미완료만 한정

## 의미와 범위

`app/lint-baseline.xml`은 첫 전체 `GitHubProdDebug` 검사에서 검토한 **372개
`MissingTranslation` 항목만** 기록합니다. Lint 전체, 특정 오류 종류 전체, 특정 디렉터리
전체를 끄지 않습니다. 새 키나 기준선에 없는 위치의 문제는 계속 검사 대상입니다.

이 기준선은 완전한 번역이나 결함 없는 앱을 뜻하지 않습니다. MVP의 한국어 지원은 시작
안내·상태·주요 탐색에 집중하며, 아직 번역하지 않은 고급 기능은 기본 영어 문자열을 사용합니다.
없는 번역을 영어 복사본으로 채워 번역 완료처럼 표시하지 않았습니다.

첫 보고서의 정확한 분류:

| 범위 | 항목 수 | 발생 원인 |
| --- | ---: | --- |
| 한국어만 누락 | 195 | 이번 포크의 부분 `values-ko` 추가로 드러난 **새 번역 부채** |
| 한국어와 기존 언어가 함께 누락 | 170 | 새 한국어 누락 + 기존 upstream 언어 누락 |
| 기존 언어만 누락 | 7 | 기존 upstream 언어 누락 |
| 합계 | **372** | 한국어가 포함된 항목 365개, 기존 다른 언어가 포함된 항목 177개 |

따라서 372개 전부를 “기존 upstream 문제”라고 설명해서는 안 됩니다. 기준선의 문자열
정의는 `app/src/main/res/values/strings.xml` 한 파일에 있으며, 항목마다 ID·메시지·소스
위치를 특정합니다. 빌드 머신의 절대 경로는 저장하지 않습니다.

별도로 새 한국어 기본 안내 문자열 파일 `values/strings_setup.xml`에는 의도한 한국어
fallback을 설명하는 **그 파일에 한정된** `MissingTranslation` 주석이 있습니다.

## 기준선에 넣지 않은 실제 오류

첫 보고서는 총 379 오류 / 156 경고였습니다. 번역 누락 이외의 다음 7개 오류는 기준선에
넣지 않았으며, 코드/리소스 수정 뒤 전체 Lint를 다시 통과시켜야 합니다.

| 검사 | 첫 보고서 위치 | 처리 방향 |
| --- | --- | --- |
| `NewApi` | `res/values/styles.xml`의 `windowLightNavigationBar` | 공통 `BaseAppTheme`와 API 27 전용 리소스로 분리 |
| `WrongConstant` | `impl/layout/DeviceLayoutDisplayMapper.kt` | 숨겨진 숫자 2037 대신 metric 조회용 공개 `TYPE_APPLICATION` 사용 |
| `RepeatOnLifecycleWrongUsage` | `ui/settings/CheatsImportProgressDialog.kt` | `onCreate`에서 collector를 한 번 등록하고 STARTED 상태에서 바인딩을 기다림 |
| `UnspecifiedRegisterReceiverFlag` | `github/services/GitHubUpdateInstallManager.kt` | `ContextCompat.registerReceiver`에 명시적 `RECEIVER_EXPORTED` 플래그 |
| `StringFormatMatches` | `values-b+es/strings.xml`의 rewind 시간 | 누락된 `%2$s`의 `%` 복구 |
| `MissingQuantity` ×2 | `values-b+ru/strings.xml`의 대기 중 성취/순위 항목 | `few`, `many` 추가 |

러시아어 추가 분기는 이미 있던 숫자 중립형 `other` 표현을 재사용합니다. 잘못된 새 굴절을
추정하지 않고 기존 의미와 `%d` 자리를 유지합니다. 한국어 `not_set`은 upstream 앱이 이미
정의한 이름을 유지하면서 해당 한국어 정의에만 `tools:override="true"`로 의도를 명시합니다.
이 선언은 AndroidX의 다른 private 리소스 경고를 끄지 않습니다.
Window context에는 [Android가 문서화한 공개 Window 타입](https://developer.android.com/reference/android/content/Context#createWindowContext(int,%20android.os.Bundle))을
사용합니다. 이러한 코드 수정과 번역 기준선은 서로 별개이며, 실제 API 오류를 기준선으로 숨기지 않았습니다.

## 유지보수 규칙

1. `./gradlew :app:lintGitHubProdDebug`를 최종 소스에서 실행하고 실제 종료 코드와 보고서를
   확인합니다. Lint는 APK 빌드만으로 자동 통과한 것으로 간주하지 않습니다.
2. 번역을 완료한 키는 기준선에서 제거하고 다시 검사합니다. 새로 남는 문제의 원인을 살피지
   않고 `updateLintBaseline`을 실행하여 모든 오류를 덮어 넣지 않습니다.
3. `scripts/tests/test_lint_baseline.py`와 소스 audit로 기준선의 개수·위치·ID가 검토 범위를
   벗어나지 않는지 검증합니다. API, lifecycle,
   권한, 형식 인수, 복수형 오류 및 경고를 이 기준선에 추가하지 않습니다.
4. 배포 검증 보고서에는 “Lint 통과(검토한 번역 누락 372개 기준선 사용)”처럼 잔여 부채를
   함께 밝힙니다. 실제 재검사가 끝나기 전 이 문서만으로 통과를 주장하지 않습니다.

기준선 사용 방식은 [Android 공식 Lint 문서](https://developer.android.com/studio/write/lint#baseline)를
참고합니다. 이 문서는 정적 검사 범위에 관한 설명이며, 실기기나 특정 게임 호환성 증거가 아닙니다.
