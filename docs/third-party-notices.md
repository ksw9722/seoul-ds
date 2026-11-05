# 출처와 서드파티 고지

원작의 파일별 저작권/라이선스 표시를 보존합니다. [전체 고지 텍스트](THIRD-PARTY-NOTICES.txt)는 아래 주요 네이티브 구성요소의 원문을 포함하며 APK 배포 자료에 같이 제공해야 합니다. 라이선스 이름만 나열하는 것으로 고지 의무가 모두 충족된다고 가정하지 않습니다.

| 구성요소 | 출처/라이선스 근거 |
|---|---|
| melonDS Android 2.0.1 | [원작](https://github.com/rafaelvcaetano/melonDS-android/tree/2.0.1), 루트 `LICENSE` GPLv3. Android 포크 전체에 `or later` 조건을 임의로 추가하지 않음 |
| melonDS 네이티브 코어 | `melonDS-android-lib/LICENSE`, 각 소스 헤더 GPL-3.0-or-later |
| 독립 FreeBIOS | `freebios/drastic_bios_readme.txt`, Gilead Kutnick 저작권 및 2조건 BSD형 허가, `bios_common.S` 원본 소스와 Makefile 동봉 |
| FAAD2 | `src/android/faad2/COPYING`, `libfaad/decoder.c` GPL-2.0-or-later 및 특별 고지 문구 |
| Oboe | `src/android/oboe/LICENSE`, Apache-2.0 |
| rcheevos | `src/android/rcheevos/LICENSE`, MIT |
| Teakra | `src/teakra/LICENSE`, MIT |
| Dolphin 유래 코드 | `src/dolphin/license_dolphin.txt` |
| blip_buf | `src/blip-buf/license.txt` |
| FatFs | `src/fatfs/LICENSE.txt` |
| libslirp | `src/net/libslirp/COPYRIGHT` 및 `src/`·`glib/`의 개별 BSD/MIT 고지, 원문/경로/해시는 [native-license-index.json](native-license-index.json) |
| xxHash | `src/xxhash/`의 Yann Collet BSD-2-Clause 원문 고지 |
| SHA-1 | `src/sha1/`의 Steve Reid Public Domain 저작자 표시 |
| libpcap 헤더 | `src/net/pcap/`의 개별 BSD 고지. 외부 동적 libpcap 바이너리를 새로 동봉하지 않음 |
| rcheevos 내 MD5 | `src/android/rcheevos/src/rhash/`의 Aladdin Enterprises / L. Peter Deutsch zlib형 허가 원문 |
| tiny-AES-c | `src/tiny-AES-c/unlicense.txt` |

**FAAD2 요구 고지:** Code from FAAD2 is copyright (c) Nero AG, www.nero.com

FreeBIOS 파일은 Nintendo에서 추출한 BIOS가 아닙니다. 원작에 포함된 재배포 가능한 대체 구현만 허용하며, 하네스는 경로뿐 아니라 SHA-256도 고정합니다. 그 외 게임/BIOS 파일을 소스 묶음에 넣지 않습니다.

## Android/JVM 실제 런타임 의존성 감사

2026-11-01 `gitHubProdDebugRuntimeClasspath`를 Gradle에서 실제 해석해 **외부 모듈 214개(BOM/메타데이터 포함), 바이너리 아티팩트 161개**를 확인했습니다. [runtime-dependencies.json](runtime-dependencies.json)에 각 좌표, POM/부모 POM 라이선스 출처, 아티팩트 SHA-256, 내장 고지 경로/해시를 기록했습니다. 미확인 POM 라이선스 오류는 0개입니다.

104개 고지 항목을 중복 제거한 13개 전체 텍스트를 종합 고지에 포함했습니다. Apache-2.0 외에 CommonMark BSD-2-Clause, Camera의 libyuv BSD-3-Clause, XZ 0BSD, Reactive Streams CC0 조건을 별도 확인했습니다. Commons Codec/IO/Compress/Lang, Jakarta Inject의 포함 NOTICE를 보존했습니다. AAR/JAR에 전체 고지가 없는 일부 항목은 [고정 버전의 공식 원문](licenses/SOURCES.md)을 추가했습니다.

```bash
# 다른 Gradle 작업과 동시에 같은 캐시를 쓰지 않도록 순차 실행합니다.
./gradlew --no-daemon --max-workers=1 \
  -I scripts/runtime-license-inventory.init.gradle :app:exportRuntimeLicenseInventory
python3 scripts/refresh_native_notices.py
python3 scripts/collect_dependency_notices.py \
  --inventory artifacts/runtime-license-inventory.json \
  --cache "$GRADLE_USER_HOME/caches/modules-2/files-2.1" --write
# 고지를 검토한 뒤 APK asset도 같은 내용으로 갱신하고 다시 빌드합니다.
cp docs/THIRD-PARTY-NOTICES.txt app/src/main/assets/licenses/THIRD-PARTY-NOTICES.txt
```

이 기록은 **해당 디버그 구성**에 대한 선언 메타데이터·고지 감사입니다. 다른 버전/릴리스 구성/새 의존성은 다시 해석·검사해야 합니다. 라이선스 메타데이터가 존재한다는 것이 법률 자문이나 모든 법적 적합성의 인증은 아닙니다. 특히 아래 PCAP 상속 이슈는 별도 배포 게이트입니다.

## 상표·이미지

Seoul DS는 원작 또는 Nintendo의 공식 제품이 아닙니다. Nintendo와 게임 제목은 권리자의 상표입니다. 원작 README의 게임 화면/스토어 배지를 이 포크의 현행 트리에서 제거했습니다. 과거 upstream Git history에는 이미지가 남아 있으므로, 새 공개 저장소는 감사한 소스 스냅샷을 기준으로 게시하고 출처 커밋을 명시하는 방식을 권장합니다.

## inherited PCAP license gate

고정된 상류 `src/net/pcap/` 일부 헤더에는 Lawrence Berkeley Laboratory(LBL) 광고 조항이 남아 있습니다. UC Berkeley 조항의 폐지 서신을 LBL 변형에도 적용할 수 있다고 임의로 가정하지 않습니다. [libpcap 원작의 공개 이슈 #1441](https://github.com/the-tcpdump-group/libpcap/issues/1441)에 관련 미해결 논의가 있습니다. 원문 고지는 보존하지만, 그것만으로 GPL 결합 배포 적합성 문제가 해결되었다고 주장하지 않습니다. Seoul DS는 루트 빌드 어댑터 `app/cmake/SeoulAndroidDependencies.cmake`로 Android에서 해당 선택적 PCAP 소스를 제외하고, 유일한 미사용 PCAP include를 제거한 생성 복사본을 사용합니다. 고정된 네이티브 하위 모듈은 수정하지 않습니다. ARM64의 실제 네이티브 링크가 완료되었고 구성 그래프400개·실제 의존성166,497줄·두 ELF의 심볼에서 PCAP 소스/헤더/심볼이 없음을 확인했습니다. 구체적인 해시·명령·범위는 [네이티브 제외 감사](testing/native-pcap-audit.md)에 기록했습니다. 원본 PCAP 파일과 고지는 대응 소스의 별도 원작 자료로 보존하며, 모든 파일에 일괄적으로 GPL만 적용된다고 주장하지 않습니다.
