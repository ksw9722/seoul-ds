#!/usr/bin/env python3
"""Prove optimized native graph settings and bind its linked ELF build IDs to APK.

This is build/package provenance evidence, not a gameplay/performance benchmark
or legal certification. Only a completed, up-to-date graph can pass.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = ("libmelonDS-lib.so", "libmelonDS-android-frontend.so")


def read_cache(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key_type, value = line.split("=", 1)
        key = key_type.split(":", 1)[0]
        values[key] = value
    return values


def require_optimized_cache(cache: dict[str, str], abi: str):
    if cache.get("CMAKE_BUILD_TYPE") != "RelWithDebInfo":
        raise ValueError("Actual CMake cache is not RelWithDebInfo")
    if cache.get("SEOUL_DS_OPTIMIZED_NATIVE", "").upper() not in {"ON", "TRUE", "1"}:
        raise ValueError("Actual CMake cache does not enable SEOUL_DS_OPTIMIZED_NATIVE")
    if cache.get("ANDROID_ABI", cache.get("CMAKE_ANDROID_ARCH_ABI")) != abi:
        raise ValueError("Actual CMake ABI differs from requested APK ABI")


def select_graph(root: Path, abi: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        directory = explicit.resolve()
        require_optimized_cache(read_cache(directory / "CMakeCache.txt"), abi)
        return directory
    matches = []
    for path in sorted((root / "app/.cxx").rglob("CMakeCache.txt")):
        try:
            require_optimized_cache(read_cache(path), abi)
            if (path.parent / "compile_commands.json").is_file():
                matches.append(path.parent)
        except ValueError:
            continue
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one optimized {abi} graph, found {len(matches)}; use --native-dir to identify the graph actually built")
    return matches[0]


def compiler_flags(arguments: list[str]) -> dict[str, str]:
    optimization = [x for x in arguments if re.fullmatch(r"-O(?:[0-3]|s|z|g|fast)?", x)]
    effective = optimization[-1] if optimization else "-O0 (implicit)"
    if effective not in {"-O2", "-O3"}:
        raise ValueError(f"Effective optimization is {effective}, not -O2/-O3")
    defines = [x for x in arguments if x in {"-DNDEBUG", "-DNDEBUG=1", "-UNDEBUG"} or x.startswith("-DNDEBUG=")]
    if not defines or defines[-1] not in {"-DNDEBUG", "-DNDEBUG=1"}:
        raise ValueError("NDEBUG is missing, undefined, or overridden")
    debug_info = [x for x in arguments if x == "-g" or re.fullmatch(r"-g[0-3]", x) or x == "-gline-tables-only"]
    if not debug_info or debug_info[-1] == "-g0":
        raise ValueError("RelWithDebInfo debug information is missing or disabled")
    return {"effective_optimization": effective, "ndebug": defines[-1], "debug_information": debug_info[-1]}


def read_gnu_build_id(stream) -> str:
    stream.seek(0)
    header = stream.read(64)
    if len(header) < 64 or header[:4] != b"\x7fELF" or header[4] not in {1, 2} or header[5] != 1:
        raise ValueError("Expected a valid little-endian ELF header")
    elf64 = header[4] == 2
    offset = struct.unpack_from("<Q" if elf64 else "<I", header, 32 if elf64 else 28)[0]
    size, count = struct.unpack_from("<HH", header, 54 if elf64 else 42)
    minimum = 56 if elf64 else 32
    if size < minimum or not 1 <= count <= 4096 or offset + size * count > 1024 * 1024:
        raise ValueError("Invalid ELF program-header table")
    stream.seek(offset)
    table = stream.read(size * count)
    if len(table) != size * count:
        raise ValueError("Truncated ELF program-header table")
    build_ids = set()
    for index in range(count):
        position = index * size
        if struct.unpack_from("<I", table, position)[0] != 4:  # PT_NOTE
            continue
        if elf64:
            note_offset = struct.unpack_from("<Q", table, position + 8)[0]
            note_size = struct.unpack_from("<Q", table, position + 32)[0]
        else:
            note_offset = struct.unpack_from("<I", table, position + 4)[0]
            note_size = struct.unpack_from("<I", table, position + 16)[0]
        if note_size > 1024 * 1024:
            raise ValueError("Unexpectedly large ELF note segment")
        stream.seek(note_offset)
        notes = stream.read(note_size)
        if len(notes) != note_size:
            raise ValueError("Truncated ELF note segment")
        cursor = 0
        while cursor + 12 <= len(notes):
            name_size, descriptor_size, kind = struct.unpack_from("<III", notes, cursor)
            cursor += 12
            descriptor_start = cursor + ((name_size + 3) & ~3)
            end = descriptor_start + descriptor_size
            next_note = descriptor_start + ((descriptor_size + 3) & ~3)
            if end > len(notes) or cursor + name_size > len(notes):
                raise ValueError("Malformed ELF note lengths")
            name = notes[cursor:cursor + name_size].rstrip(b"\0")
            if name == b"GNU" and kind == 3 and descriptor_size:
                build_ids.add(notes[descriptor_start:end].hex())
            cursor = next_note
    if len(build_ids) != 1:
        raise ValueError(f"Expected one GNU build ID, found {len(build_ids)}")
    return next(iter(build_ids))


def run_checked(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=120).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64", "armeabi-v7a"), default="arm64-v8a")
    parser.add_argument("--native-dir", type=Path, help="Explicit completed CMake graph; required if multiple optimized graphs exist")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = {"status": "FAIL", "abi": args.abi, "scope": "Configured effective native flags + completed Ninja graph + PCAP exclusion evidence + GNU build-ID binding to APK; not runtime or performance proof"}
    try:
        directory = select_graph(ROOT, args.abi, args.native_dir)
        cache = read_cache(directory / "CMakeCache.txt")
        report["native_graph"] = str(directory.relative_to(ROOT)) if directory.is_relative_to(ROOT) else str(directory)
        report["cmake_build_type"] = cache["CMAKE_BUILD_TYPE"]
        report["optimized_native_cache"] = cache["SEOUL_DS_OPTIMIZED_NATIVE"]
        commands_path = directory / "compile_commands.json"
        commands_bytes = commands_path.read_bytes()
        commands = json.loads(commands_bytes)
        report["compile_commands_sha256"] = hashlib.sha256(commands_bytes).hexdigest()
        report["configured_compile_units"] = len(commands)
        if not commands:
            raise ValueError("Empty compiler graph")
        flags = []
        names = set()
        for entry in commands:
            source = Path(entry["file"])
            if "pcap" in source.name.lower():
                raise ValueError(f"PCAP source remains in native compiler graph: {source.name}")
            if source.suffix.lower() not in {".c", ".cc", ".cpp", ".cxx"}:
                continue
            arguments = entry.get("arguments") or shlex.split(entry["command"])
            try:
                result = compiler_flags(arguments)
            except ValueError as exc:
                raise ValueError(f"{source.name}: {exc}") from exc
            names.add(source.name)
            flags.append(result)
        if not {"NDS.cpp", "MelonDSAndroidJNI.cpp"}.issubset(names):
            raise ValueError("Graph lacks core/JNI proof units")
        report["configured_c_cpp_units_validated"] = len(flags)
        report["effective_optimization_counts"] = {flag: sum(x["effective_optimization"] == flag for x in flags) for flag in ("-O2", "-O3")}
        report["configured_not_built_count_note"] = "Compile database may include unused library variants; this count is not a claim that every configured unit was built"
        ninja = Path(cache["CMAKE_MAKE_PROGRAM"])
        nm = Path(cache["CMAKE_NM"])
        dry_run = run_checked([str(ninja), "-C", str(directory), "-n", "melonDS-android-frontend"])
        if "no work to do" not in dry_run.lower() or re.search(r"\[\d+/\d+\]", dry_run):
            raise ValueError("Native target is not up to date; finish its build before validation")
        report["ninja_target_up_to_date"] = True
        dependencies = run_checked([str(ninja), "-C", str(directory), "-t", "deps"])
        if not dependencies.strip():
            raise ValueError("No actual compiler dependency data")
        if re.search(r"[/\\]pcap[/\\]|Net_PCap\.(?:h|cpp)", dependencies, re.I):
            raise ValueError("PCAP source/header remains in actual dependencies")
        report["actual_dependency_lines"] = len(dependencies.splitlines())
        report["pcap_dependency_matches"] = 0
        output_dir = Path(cache["CMAKE_LIBRARY_OUTPUT_DIRECTORY"])
        report["libraries"] = {}
        with zipfile.ZipFile(args.apk) as apk:
            for name in LIBRARIES:
                source = output_dir / name
                with source.open("rb") as file:
                    source_id = read_gnu_build_id(file)
                with apk.open(f"lib/{args.abi}/{name}") as file:
                    apk_id = read_gnu_build_id(file)
                if source_id != apk_id:
                    raise ValueError(f"Stale or wrong graph/APK pair: {name} GNU build IDs differ")
                symbols = run_checked([str(nm), "--demangle", str(source)])
                if "pcap" in symbols.lower():
                    raise ValueError(f"PCAP symbol remains in {name}")
                report["libraries"][name] = {"unstripped_elf_bytes": source.stat().st_size, "graph_gnu_build_id": source_id, "apk_gnu_build_id": apk_id, "build_ids_match": True, "pcap_symbols": "NONE"}
        report["status"] = "PASS"
    except (OSError, ValueError, KeyError, struct.error, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        report["error"] = str(exc)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS")

if __name__ == "__main__":
    sys.exit(main())
