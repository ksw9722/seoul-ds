#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate this bounded original fixture, not arbitrary third-party ROMs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct

ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def crc16(data: bytes | bytearray) -> int:
    # Table-based implementation independent from the packer's bitwise loop.
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 * (value & 1))
        table.append(value)
    result = 0xFFFF
    for value in data:
        result = (result >> 8) ^ table[(result ^ value) & 0xFF]
    return result


def read16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def read32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def title(data: bytes) -> str:
    return data.decode("utf-16le").split("\x00", 1)[0]


def validate_bytes(rom: bytes) -> dict:
    require(crc16(b"123456789") == 0x4B37, "CRC implementation failed known vector")
    require(len(rom) == 128 * 1024, "Fixture must be exactly 128 KiB")
    require(rom[:12] == b"SEOULDS TEST" and rom[12:16] == b"####", "Unexpected original-fixture identity")
    require(rom[0x12] == 0 and rom[0x14] == 0, "Expected DS-only / 128 KiB capacity header")
    require(rom[0xC0:0x15C] == bytes(156), "Boot-logo area must remain entirely zero")
    require(read16(rom, 0x15C) == crc16(rom[0xC0:0x15C]), "Zero-logo CRC mismatch")
    require(read16(rom, 0x15E) == crc16(rom[:0x15E]), "Header CRC mismatch")
    require(read32(rom, 0x84) == 0x200, "Unexpected header size")
    regions = [(0, 0x200, "header")]
    layout = {}
    for name, offset, address in (("arm9", 0x20, 0x02000000), ("arm7", 0x30, 0x02380000)):
        start, entry, ram, size = struct.unpack_from("<IIII", rom, offset)
        require(start >= 0x200 and start % 0x200 == 0, f"{name}: invalid ROM alignment")
        require(size > 0 and size % 4 == 0 and start + size <= len(rom), f"{name}: invalid size")
        require(entry == ram == address, f"{name}: wrong ARM entry/RAM address")
        require(any(rom[start:start + size]), f"{name}: empty payload")
        regions.append((start, start + size, name))
        layout[name] = {"rom_offset": start, "size": size, "entry": entry}
    require(layout["arm9"]["rom_offset"] < 0x4000, "Direct-boot homebrew offset was lost")
    banner_offset = read32(rom, 0x68)
    require(banner_offset > 0 and banner_offset % 0x200 == 0, "Banner must have a positive aligned offset")
    require(banner_offset + 0xA40 <= len(rom), "Banner is truncated")
    require(read32(rom, 0x80) == banner_offset + 0xA40, "Used-ROM size mismatch")
    regions.append((banner_offset, banner_offset + 0xA40, "banner"))
    for current, following in zip(sorted(regions), sorted(regions)[1:]):
        require(current[1] <= following[0], f"Overlapping regions: {current[2]} / {following[2]}")
    banner = rom[banner_offset:banner_offset + 0xA40]
    require(read16(banner, 0) == 3, "Expected version 3 multilingual banner")
    banner_crcs = []
    for field, end in ((2, 0x840), (4, 0x940), (6, 0xA40)):
        calculated = crc16(banner[0x20:end])
        require(read16(banner, field) == calculated, f"Banner CRC at {field:#x} mismatch")
        banner_crcs.append(calculated)
    require(len(set(banner[0x20:0x220])) >= 4, "Expected nonempty geometric icon tile data")
    english = title(banner[0x340:0x440])
    korean = title(banner[0x940:0xA40])
    require(english.startswith("Seoul DS Test\n") and "GPL-3.0-only" in english, "English banner title missing")
    require("테스트" in korean and "GPL-3.0-only" in korean, "Korean banner title missing")
    return {
        "format_status": "PASS",
        "runtime_status": "NOT RUN",
        "size": len(rom),
        "sha256": hashlib.sha256(rom).hexdigest(),
        "header_crc16": read16(rom, 0x15E),
        "zero_logo_crc16": read16(rom, 0x15C),
        "banner_crc16": banner_crcs,
        "banner_offset": banner_offset,
        "layout": layout,
        "english_title": english,
        "korean_title": korean,
        "proprietary_boot_logo": "ABSENT (156 zero bytes)",
    }


def validate_manifest(path: Path, rom: bytes) -> int:
    manifest = json.loads(path.read_text())
    require(manifest["license"] == "GPL-3.0-only", "Fixture license mismatch")
    require(manifest["rom_sha256"] == hashlib.sha256(rom).hexdigest(), "ROM hash mismatch")
    expected_sources = {str(p.relative_to(ROOT)) for p in (ROOT / "tests/homebrew").iterdir() if p.is_file()}
    expected_sources.add("LICENSE")
    require(set(manifest["source_sha256"]) == expected_sources, "Source manifest is incomplete or contains extra inputs")
    for name, expected in manifest["source_sha256"].items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe manifest source path")
        source = (ROOT / name).resolve()
        require(source.is_relative_to(ROOT), "Source path escapes repository")
        require(hashlib.sha256(source.read_bytes()).hexdigest() == expected, f"Source hash changed: {name}")
    return len(expected_sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    data = args.rom.read_bytes()
    result = validate_bytes(data)
    if args.manifest:
        result["source_hashes_verified"] = validate_manifest(args.manifest, data)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
