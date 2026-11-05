# Android PCAP 제외 증거

범위는 **실제 컴파일 그래프, 컴파일러 의존성 데이터베이스, 생성된 네이티브 ELF 심볼**입니다. 저작권/라이선스 법률 의견이나 앱 전체의 모든 라이선스 적합성 인증이 아닙니다. 원본 PCAP 헤더는 고정된 상류 소스의 자료와 고지로 보존하되 Android 바이너리에 컴파일하지 않습니다.

## 2026-11-01 권장 최적화 ARM64 결과

[실제 최적화 증거](optimized-native-proof-arm64.json)는 완료된 RelWithDebInfo 그래프의 구성 단위 400개(그중 C/C++ 399개), 실제 Ninja 의존성 166,617줄, 두 ELF 심볼에서 PCAP 흔적이 없음을 확인했다. 실제 빌드 단계 수는 294개이며 구성 단위 수와 구분한다.

- core GNU build ID: `259fa15643c0f6f010650150a276dff74cfeb163`
- frontend GNU build ID: `3d666eb21ca8de8a83c11284bd62f0196dcd31be`

각 ID는 권장 최적화 APK에 들어간 라이브러리의 ID와 일치한다. strip 전후 다른 파일 해시 대신 GNU build ID로 실제 최적화 그래프와 패키지의 연결을 확인한다. 실제 APK 전체 해시는 [패키지 검증](apk-validation-arm64.json)에 기록했다.

## 2026-11-01 이전 비최적화 개발 프로필 결과

`native-pcap-audit-arm64.log`를 확인했습니다.

- ARM64 compile command 400개, PCAP compilation unit 0개.
- 실제 Ninja 의존성 출력 166,497줄, PCAP header dependency 0개.
- `libmelonDS-lib.so`(72,027,800바이트), `libmelonDS-android-frontend.so`(1,629,424바이트)의 실제 **unstripped** ELF에서 PCAP 심볼 없음.
- 네이티브 링크는 standalone Ninja 순차 복구에서 완료했습니다. 이는 APK 패키징·서명·UI·게임 실행 성공과는 별도입니다.

| 실제 비스트립 ELF | SHA-256 |
|---|---|
| libmelonDS-lib.so | `2c45bb14bf459e11da1bba12fa6397f0838afe802ed007d55c392e8a9e7fe505` |
| libmelonDS-android-frontend.so | `422a02f16912991a42f72b9938b7f935041606044cf79658a3b303b4d0d4afbb` |

APK 패키징 과정에서 strip되는 라이브러리의 해시는 위 값과 다를 수 있으므로 APK 전체 해시와 혼동하지 마세요.

## 재현 방법

먼저 해당 ABI의 실제 네이티브 빌드를 마칩니다. 방금 빌드한 `.cxx` 해시 경로를 확인해 지정하고, 오래된 다른 설정/ABI의 그래프를 대신 검사하지 않습니다.

```bash
NATIVE_DIR=app/.cxx/Debug/ACTUAL_GENERATED_HASH/arm64-v8a
OBJ_DIR=app/build/intermediates/cxx/Debug/ACTUAL_GENERATED_HASH/obj/arm64-v8a
NINJA="$ANDROID_HOME/cmake/3.22.1/bin/ninja"
NM="$ANDROID_HOME/ndk/28.0.13004108/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm"
mkdir -p artifacts/native-audit

# 그래프에 PCAP translation unit이 들어 있지 않아야 합니다.
python3 - "$NATIVE_DIR/compile_commands.json" <<'PY'
import json, sys
from pathlib import Path
commands = json.loads(Path(sys.argv[1]).read_text())
assert commands, "Empty compile graph"
assert not any("pcap" in Path(c["file"]).name.lower() for c in commands), "PCAP source compiled"
print("PASS: compile units", len(commands), "PCAP units 0")
PY

# 각 소스의 실제 컴파일러 header dependency도 검사합니다.
"$NINJA" -C "$NATIVE_DIR" -t deps > artifacts/native-audit/dependencies.txt
test -s artifacts/native-audit/dependencies.txt
if grep -Ei '/pcap/|Net_PCap\.(h|cpp)' artifacts/native-audit/dependencies.txt; then
  echo 'FAIL: PCAP header/source dependency found'; exit 1
fi

# 심볼이 남아 있다면 빌드 제외가 불완전할 수 있습니다.
"$NM" --demangle "$OBJ_DIR/libmelonDS-lib.so" \
  "$OBJ_DIR/libmelonDS-android-frontend.so" > artifacts/native-audit/symbols.txt
test -s artifacts/native-audit/symbols.txt
if grep -i 'pcap' artifacts/native-audit/symbols.txt; then
  echo 'FAIL: PCAP symbol found'; exit 1
fi
sha256sum "$OBJ_DIR/libmelonDS-lib.so" "$OBJ_DIR/libmelonDS-android-frontend.so"
echo 'PASS: PCAP excluded in graph, actual dependencies and native symbols'
```

빌드 어댑터는 예상한 `Net_PCap.cpp` 소스와 `PlatformAndroid.cpp`의 미사용 PCAP include가 각각 정확히 하나인지를 확인하며, 모양이 바뀌면 조용히 계속하지 않고 구성 단계에서 실패합니다. 새 상류 버전·새 ABI·빌드 설정 변경 후에는 이 검사를 다시 해야 합니다.
