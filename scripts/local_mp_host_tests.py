#!/usr/bin/env python3
"""Exercise actual LocalMP with host platform primitives, not a game/runtime test."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

root = Path(__file__).resolve().parents[1]
compiler = shutil.which("g++")
if not compiler:
    print("BLOCKED: g++ required", file=sys.stderr)
    raise SystemExit(2)
with tempfile.TemporaryDirectory(prefix="seoul-ds-local-mp-") as tmp:
    for name, flags in (("debug", ["-O0"]), ("release", ["-O2", "-DNDEBUG"])):
        binary = Path(tmp) / name
        subprocess.run([compiler, "-std=c++17", "-pthread", *flags,
                        "-I", str(root / "melonDS-android-lib/src"),
                        "-I", str(root / "melonDS-android-lib/src/net"),
                        str(root / "app/src/test/cpp/LocalMPTest.cpp"),
                        str(root / "melonDS-android-lib/src/net/LocalMP.cpp"),
                        "-o", str(binary)], check=True, timeout=120)
        print(f"PROFILE: {name}", flush=True)
        subprocess.run([str(binary)], check=True, timeout=30)
