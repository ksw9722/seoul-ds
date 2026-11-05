#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# All generated files stay below the ignored artifacts/homebrew directory.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
OUT="$ROOT/artifacts/homebrew"
SDK="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-${SDK}/ndk/28.0.13004108}}"
BIN="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin"
[[ -x "$BIN/clang" && -x "$BIN/llvm-objcopy" ]] || {
    echo "Set ANDROID_NDK_HOME to installed NDK 28.0.13004108 (Linux x86_64)." >&2
    exit 2
}
grep -Eq '^Pkg.Revision = 28\.0\.13004108$' "$NDK/source.properties" || {
    echo "This deterministic fixture requires NDK 28.0.13004108." >&2
    exit 2
}
[[ ! -L "$ROOT/artifacts" && ! -L "$OUT" ]] || {
    echo "Refusing a symlinked artifact output directory." >&2
    exit 2
}
mkdir -p -- "$OUT"
STAGE="$(mktemp -d "$OUT/.build.XXXXXX")"
trap 'rm -rf -- "$STAGE"' EXIT

COMMON=(--target=arm-none-eabi -marm -ffreestanding -fno-builtin -fno-pic -fno-pie
    -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables
    -ffunction-sections -fdata-sections -nostdlib -fuse-ld=lld -Os
    -Wall -Wextra -Werror -Wl,--build-id=none -Wl,--gc-sections -Wl,--no-undefined)
"$BIN/clang" "${COMMON[@]}" -mcpu=arm946e-s -Wl,-T,"$SCRIPT_DIR/arm9.ld" \
    "$SCRIPT_DIR/arm9_start.S" "$SCRIPT_DIR/arm9.c" -o "$STAGE/arm9.elf"
"$BIN/clang" "${COMMON[@]}" -mcpu=arm7tdmi -Wl,-T,"$SCRIPT_DIR/arm7.ld" \
    "$SCRIPT_DIR/arm7.S" -o "$STAGE/arm7.elf"
"$BIN/llvm-objcopy" -O binary "$STAGE/arm9.elf" "$STAGE/arm9.bin"
"$BIN/llvm-objcopy" -O binary "$STAGE/arm7.elf" "$STAGE/arm7.bin"
"$BIN/clang" --version > "$STAGE/toolchain.txt"
python3 -B "$SCRIPT_DIR/pack_nds.py" "$STAGE" "$OUT"
python3 -B "$SCRIPT_DIR/validate_nds.py" "$OUT/seoul-ds-test.nds" --manifest "$OUT/manifest.json" \
    | tee "$OUT/validation.json"
