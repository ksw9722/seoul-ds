#!/usr/bin/env python3
"""Validate development APK identity/ABI/signature/notices, without launching it."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ABI_ELF = {"arm64-v8a": (2, 183), "x86_64": (2, 62), "armeabi-v7a": (1, 40)}

def validate_elf_header(data: bytes, abi: str) -> bool:
    if len(data) < 20 or data[:4] != b"\x7fELF" or data[5] != 1:
        return False
    elf_class, machine = ABI_ELF[abi]
    return data[4] == elf_class and struct.unpack("<H", data[18:20])[0] == machine

def elf_program_table_bounds(header: bytes) -> tuple[int, int, int]:
    if len(header) < 64:
        raise ValueError("Truncated ELF header")
    if header[4] == 2:
        offset = struct.unpack_from("<Q", header, 32)[0]
        size, count = struct.unpack_from("<HH", header, 54)
        minimum = 56
    else:
        offset = struct.unpack_from("<I", header, 28)[0]
        size, count = struct.unpack_from("<HH", header, 42)
        minimum = 32
    if size < minimum or count < 1 or count > 4096 or offset + size * count > 1024 * 1024:
        raise ValueError("Invalid or unexpectedly large ELF program-header table")
    return offset, size, count

def validate_load_alignment(data: bytes, abi: str) -> list[dict]:
    if not validate_elf_header(data, abi):
        raise ValueError("ELF architecture mismatch")
    offset, size, count = elf_program_table_bounds(data)
    if len(data) < offset + size * count:
        raise ValueError("Truncated ELF program-header table")
    required = 16384 if abi in {"arm64-v8a", "x86_64"} else 4096
    segments = []
    for index in range(count):
        position = offset + index * size
        kind = struct.unpack_from("<I", data, position)[0]
        if kind != 1:  # PT_LOAD
            continue
        if data[4] == 2:
            file_offset, virtual_address = struct.unpack_from("<QQ", data, position + 8)
            alignment = struct.unpack_from("<Q", data, position + 48)[0]
        else:
            file_offset, virtual_address = struct.unpack_from("<II", data, position + 4)
            alignment = struct.unpack_from("<I", data, position + 28)[0]
        if alignment < required or alignment & (alignment - 1) or (virtual_address - file_offset) % required:
            raise ValueError(f"ELF LOAD segment {index} is not {required}-byte page aligned")
        segments.append({"index": index, "alignment": alignment, "required": required})
    if not segments:
        raise ValueError("No ELF PT_LOAD segment found")
    return segments

def check_zip(apk: Path, abi: str, root: Path = ROOT) -> dict:
    with zipfile.ZipFile(apk) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt ZIP member: {bad}")
        libraries = [n for n in archive.namelist() if n.startswith("lib/") and n.endswith(".so")]
        expected = f"lib/{abi}/libmelonDS-android-frontend.so"
        if expected not in libraries:
            raise ValueError(f"Missing native emulator frontend: {expected}")
        alignment_report = {}
        for name in libraries:
            if name.split("/")[1] != abi:
                raise ValueError(f"Unexpected ABI in single-ABI build: {name}")
            with archive.open(name) as stream:
                header = stream.read(64)
                if not validate_elf_header(header, abi):
                    raise ValueError(f"Native ELF architecture mismatch: {name}")
                offset, size, count = elf_program_table_bounds(header)
                stream.seek(0)
                alignment_report[name] = validate_load_alignment(stream.read(offset + size * count), abi)
        for source, member in (("LICENSE", "assets/licenses/GPL-3.0.txt"), ("docs/THIRD-PARTY-NOTICES.txt", "assets/licenses/THIRD-PARTY-NOTICES.txt")):
            if archive.read(member) != (root / source).read_bytes():
                raise ValueError(f"Packaged license differs from audited source: {member}")
        forbidden = [n for n in archive.namelist() if Path(n).suffix.lower() in {".nds", ".srl", ".sav", ".dsv", ".jks", ".keystore"}]
        if forbidden:
            raise ValueError("Unexpected game/save/signing material inside APK: " + ", ".join(forbidden))
    return {"native_libraries": libraries, "elf_load_alignment": alignment_report, "zip_crc": "PASS", "license_assets": "byte-identical to source"}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--abi", choices=tuple(ABI_ELF), default="arm64-v8a")
    parser.add_argument("--sdk", type=Path, default=Path(os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", "/missing-android-sdk"))))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = {"status": "FAIL", "apk": args.apk.name, "abi": args.abi, "scope": "Package validation only; no installation or emulation performed"}
    try:
        if not args.apk.is_file():
            raise ValueError("Expected APK file does not exist")
        report.update(check_zip(args.apk, args.abi))
        build_tools = args.sdk / "build-tools/36.0.0"
        for tool in ("aapt", "apksigner", "zipalign"):
            if not (build_tools / tool).is_file():
                raise ValueError(f"Missing official Android package validation tool: {tool}")
        badging = subprocess.run([str(build_tools / "aapt"), "dump", "badging", str(args.apk)], check=True, capture_output=True, text=True, timeout=60).stdout
        package = re.search(r"package: name='([^']+)'", badging)
        minimum = re.search(r"^sdkVersion:'([^']+)'", badging, re.M)
        target = re.search(r"^targetSdkVersion:'([^']+)'", badging, re.M)
        if not package or package[1] != "io.github.seoulds.emulator.dev":
            raise ValueError("APK application ID is not the independent development package")
        if not minimum or minimum[1] != "24" or not target or target[1] != "36":
            raise ValueError("APK SDK levels differ from min24/target36")
        report.update(application_id=package[1], min_sdk=minimum[1], target_sdk=target[1])
        subprocess.run([str(build_tools / "zipalign"), "-c", "-P", "16", "4", str(args.apk)], check=True, capture_output=True, text=True, timeout=60)
        report["zip_alignment"] = "PASS: zipalign -c -P 16 4 (16 KiB native-library page alignment)"
        signature = subprocess.run([str(build_tools / "apksigner"), "verify", "--verbose", "--print-certs", str(args.apk)], check=True, capture_output=True, text=True, timeout=60)
        certificates = re.findall(r"certificate SHA-256 digest: ([0-9a-f]+)", signature.stdout)
        if not certificates:
            raise ValueError("Signature verified but certificate SHA-256 digest was not reported")
        report.update(signature="VERIFIED (development build, not a production signing policy)", signer_certificate_sha256=certificates)
        report["bytes"] = args.apk.stat().st_size
        digest = hashlib.sha256()
        with args.apk.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(block)
        report["sha256"] = digest.hexdigest()
        report["status"] = "PASS"
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        report["error"] = str(exc)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS")

if __name__ == "__main__":
    sys.exit(main())
