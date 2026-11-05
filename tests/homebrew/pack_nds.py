#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Assemble only the original local test programs and a generated geometric banner."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
ARM9_ADDRESS = 0x02000000
ARM7_ADDRESS = 0x02380000
BANNER_SIZE = 0xA40


def crc16(data: bytes | bytearray) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def colour(r: int, g: int, b: int) -> int:
    return r | (g << 5) | (b << 10)


def make_banner() -> bytearray:
    banner = bytearray(BANNER_SIZE)
    struct.pack_into("<H", banner, 0, 3)  # Eight UTF-16 title slots, including Korean.
    # Original two-window icon. No imported image or platform logo is involved.
    pixels = [[1 for _ in range(32)] for _ in range(32)]
    for top, bottom, fill in ((3, 14, 2), (17, 28, 3)):
        for y in range(top, bottom + 1):
            for x in range(4, 28):
                pixels[y][x] = 4 if x in (4, 27) or y in (top, bottom) else fill
    for tile_y in range(4):
        for tile_x in range(4):
            tile_offset = 0x20 + (tile_y * 4 + tile_x) * 32
            for y in range(8):
                for x in range(0, 8, 2):
                    left = pixels[tile_y * 8 + y][tile_x * 8 + x]
                    right = pixels[tile_y * 8 + y][tile_x * 8 + x + 1]
                    banner[tile_offset + y * 4 + x // 2] = left | (right << 4)
    palette = [0, colour(3, 5, 10), colour(4, 20, 24), colour(31, 17, 4), colour(29, 30, 31)]
    for index, value in enumerate(palette):
        struct.pack_into("<H", banner, 0x220 + index * 2, value)
    english = "Seoul DS Test\nOriginal homebrew\nGPL-3.0-only"
    korean = "Seoul DS 테스트\n직접 만든 홈브루\nGPL-3.0-only"
    for language in range(8):
        encoded = (korean if language == 7 else english).encode("utf-16le")
        if len(encoded) > 254:
            raise ValueError("Banner title must leave a UTF-16 terminator")
        offset = 0x240 + language * 0x100
        banner[offset:offset + len(encoded)] = encoded
    for crc_offset, end in ((2, 0x840), (4, 0x940), (6, 0xA40)):
        struct.pack_into("<H", banner, crc_offset, crc16(banner[0x20:end]))
    return banner


def check_elf(path: Path, expected_entry: int) -> None:
    data = path.read_bytes()
    if data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError(f"Not a 32-bit little-endian ELF: {path.name}")
    if struct.unpack_from("<H", data, 18)[0] != 40:
        raise ValueError("ELF is not ARM")
    if struct.unpack_from("<I", data, 24)[0] != expected_entry:
        raise ValueError("ELF entry does not match direct-boot header")


def padded(data: bytes) -> bytes:
    return data + bytes((-len(data)) % 4)


def main() -> None:
    stage, output = (Path(arg).resolve() for arg in sys.argv[1:])
    allowed = (ROOT / "artifacts/homebrew").resolve()
    if output != allowed or stage.parent != allowed:
        raise ValueError("Generated files must stay under artifacts/homebrew")
    check_elf(stage / "arm9.elf", ARM9_ADDRESS)
    check_elf(stage / "arm7.elf", ARM7_ADDRESS)
    arm9 = padded((stage / "arm9.bin").read_bytes())
    arm7 = padded((stage / "arm7.bin").read_bytes())
    arm9_offset = 0x200
    arm7_offset = (arm9_offset + len(arm9) + 0x1FF) & ~0x1FF
    banner_offset = max(0x1000, (arm7_offset + len(arm7) + 0x1FF) & ~0x1FF)
    used_size = banner_offset + BANNER_SIZE
    if arm7_offset >= 0x4000 or used_size > 128 * 1024:
        raise ValueError("Fixture payload unexpectedly exceeds its bounded layout")
    rom = bytearray(128 * 1024)
    rom[:12] = b"SEOULDS TEST"
    rom[12:16] = b"####"  # Homebrew identifier recognized by the pinned core.
    rom[16:18] = b"00"
    struct.pack_into("<IIII", rom, 0x20, arm9_offset, ARM9_ADDRESS, ARM9_ADDRESS, len(arm9))
    struct.pack_into("<IIII", rom, 0x30, arm7_offset, ARM7_ADDRESS, ARM7_ADDRESS, len(arm7))
    struct.pack_into("<I", rom, 0x68, banner_offset)
    struct.pack_into("<II", rom, 0x80, used_size, 0x200)
    # The boot-logo area is intentionally all zero, not a Nintendo boot asset.
    struct.pack_into("<H", rom, 0x15C, crc16(rom[0xC0:0x15C]))
    struct.pack_into("<H", rom, 0x15E, crc16(rom[:0x15E]))
    rom[arm9_offset:arm9_offset + len(arm9)] = arm9
    rom[arm7_offset:arm7_offset + len(arm7)] = arm7
    rom[banner_offset:used_size] = make_banner()
    name = "seoul-ds-test.nds"
    (output / name).write_bytes(rom)
    inputs = sorted(path for path in Path(__file__).parent.iterdir() if path.is_file())
    source_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    source_hashes["LICENSE"] = hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest()
    manifest = {
        "schema": 1,
        "license": "GPL-3.0-only",
        "rom": name,
        "rom_sha256": hashlib.sha256(rom).hexdigest(),
        "source_sha256": source_hashes,
        "toolchain": (stage / "toolchain.txt").read_text().splitlines()[0],
        "ndk": "28.0.13004108",
        "runtime_status": "NOT RUN; build and format checks are not emulation evidence",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
