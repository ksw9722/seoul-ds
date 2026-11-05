# 직접 만든 DS 테스트 홈브루

이 폴더의 소스는 Seoul DS를 위해 새로 작성한 **GPL-3.0-only 테스트 코드**입니다.
라이선스 전문은 저장소의 [`LICENSE`](../../LICENSE)에 있습니다. 외부 게임, BIOS,
상용 부팅 로고, 게임 아트워크, devkitPro 코드·라이브러리를 포함하거나 내려받지 않습니다.
배너의 두 직사각형 아이콘도 빌드 스크립트가 직접 생성합니다.

**빌드·파일 구조 검사 성공은 실행 성공이 아닙니다.** 실제 에뮬레이터 검증 결과는 별도
테스트 보고서에 기록해야 합니다. Galaxy S24 또는 특정 상용 게임 호환성의 증거가 아닙니다.

## 범위

- ARM9: 두 화면의 단색 배경, A/B의 눌림 전환 감지, RAM에 보관한 두 색상 상태.
- ARM7: 인터럽트를 끈 대기 루프. 오디오·터치·파일 시스템·통신 기능은 없습니다.
- A를 한 번 눌렀다 놓으면 **위 화면**이 청록색 ↔ 분홍색으로 바뀝니다.
- B를 한 번 눌렀다 놓으면 **아래 화면**이 주황색 ↔ 보라색으로 바뀝니다.
- 버튼을 계속 누르면 반복 전환하지 않습니다. A/B 외 입력의 검증용이 아닙니다.
- 에뮬레이터 **상태 저장/불러오기**로 두 색상이 돌아오는지를 확인하기 위한 fixture입니다.
  카트리지 저장(SRAM/게임 안의 저장), 오디오, 터치, 정확한 타이밍은 검증하지 않습니다.

| 상태 | RGB 5비트 채널 (R, G, B) |
| --- | --- |
| 위 초기 / A 전환 | `(4,20,24)` / `(31,6,18)` |
| 아래 초기 / B 전환 | `(31,17,4)` / `(12,7,27)` |

## 빌드 및 정적 검증

이미 승인·설치한 **Android NDK 28.0.13004108**, Linux x86_64, Bash, Python 3.10+를
사용합니다. Clang을 freestanding ARM 컴파일러로 사용하므로 Android 라이브러리나
devkitARM 런타임은 링크하지 않습니다. 이 스크립트는 라이선스 동의나 다운로드를 하지 않습니다.

```sh
ANDROID_NDK_HOME=/path/to/android-sdk/ndk/28.0.13004108 \
  bash tests/homebrew/build.sh
python3 -B tests/homebrew/test_format.py
```

`ANDROID_SDK_ROOT` 또는 `ANDROID_HOME` 아래의 고정 NDK 경로도 지원합니다.
생성물은 Git에서 무시되는 `artifacts/homebrew/`에만 놓입니다:

- `seoul-ds-test.nds`: 128 KiB의 원본 테스트 프로그램
- `manifest.json`: ROM SHA-256, 소스별 SHA-256, 툴체인 식별 정보
- `validation.json`: 헤더·배너 CRC, 영역 정렬/경계/중복, 소스 해시 검사 결과

두 번 빌드하여 `.nds`와 manifest의 SHA-256이 같은지도 비교할 수 있습니다. 시간·임시
경로·임의 값은 ROM에 넣지 않습니다. 소스를 바꾸면 다시 빌드해야 manifest 검사가 통과합니다.

## 선택적 실행 절차 — 실행 결과를 꾸며 쓰지 않기

1. 자신이 빌드한 fixture만 기기/에뮬레이터의 테스트 폴더로 복사하고 앱의 폴더 선택기로 엽니다.
2. **DS + 내부 FreeBIOS + 직접 실행**을 사용합니다. 헤더의 156바이트 부팅 로고 영역은
   의도적으로 전부 0이며, 실제 펌웨어 메뉴 부팅이나 하드웨어 카트리지 부팅용 이미지가 아닙니다.
3. 초기 위 청록색 / 아래 주황색을 기록합니다. A, B 각각 눌렀다 놓아 독립적인 색상 전환을 확인합니다.
4. 버튼을 모두 놓고 상태를 저장합니다. A/B로 색을 바꾼 뒤 상태를 불러왔을 때 저장했던 두 색이
   복원되는지 확인합니다. 앱 일시 정지·재개도 별도로 기록합니다.
5. 수행하지 못한 항목은 `NOT RUN`, 실패는 `FAIL`로 남깁니다. 성공하더라도 다른 게임의 호환성이나
   실제 게임 저장 신뢰성으로 확대 해석하지 않습니다.

## 형식과 구현 근거

기능상 필요한 레지스터 주소·비트·파일 형식만 아래 공개 소스와 대조했습니다. 아래 라이브러리의
구현, 부팅 코드, 로고 배열은 복사하거나 링크하지 않았습니다.

- [고정 melonDS 헤더/홈브루 식별](../../melonDS-android-lib/src/NDS_Header.h)
- [고정 melonDS 직접 부팅](../../melonDS-android-lib/src/NDS.cpp)
- [고정 melonDS 배경색 렌더링](../../melonDS-android-lib/src/GPU2D_Soft.cpp)
- [libnds 비디오 레지스터 설명](https://github.com/devkitPro/libnds/blob/master/include/nds/arm9/video.h)
- [Calico LCD 전원/화면 배치 비트](https://github.com/devkitPro/calico/blob/master/include/calico/nds/pm.h)
- [ndstool 배너 크기 정의](https://github.com/devkitPro/ndstool/blob/master/source/banner.h)

검증기는 `####` 홈브루 코드, `ARM9ROMOffset < 0x4000`, 0으로 채운 로고, 버전 3 배너의
영어/한국어 UTF-16 제목과 세 CRC를 요구합니다. 앱 스캐너가 읽는 배너의 `0xA00` 바이트 및
영어 제목 `0x340`도 파일 안에 포함됩니다.
