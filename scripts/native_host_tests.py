#!/usr/bin/env python3
"""Compile and run host-only C++ state synchronization tests; no Android/ROM."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
compiler = shutil.which("g++")
if not compiler:
    print("BLOCKED: host g++ is required for native synchronization tests", file=sys.stderr)
    sys.exit(2)
with tempfile.TemporaryDirectory(prefix="seoul-ds-native-") as directory:
    for profile, flags in (("unoptimized", ["-O0"]), ("optimized-ndebug", ["-O2", "-DNDEBUG"])):
        binary = Path(directory) / f"paused-state-access-{profile}"
        command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread", *flags, str(ROOT / "app/src/test/cpp/PausedStateAccessTest.cpp"), "-o", str(binary)]
        print(f"PROFILE: {profile}; same 5 behavioral cases, always-on checks", flush=True)
        print("COMPILE: " + " ".join(command), flush=True)
        subprocess.run(command, check=True, timeout=120)
        subprocess.run([str(binary)], check=True, timeout=30)
