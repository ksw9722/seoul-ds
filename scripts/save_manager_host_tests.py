#!/usr/bin/env python3
"""Host-test actual SaveManager against synthetic platform file failures."""
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
with tempfile.TemporaryDirectory(prefix="seoul-ds-save-") as tmp:
    for profile, flags in (("debug", ["-O0"]), ("release", ["-O2", "-DNDEBUG"])):
        binary = Path(tmp) / profile
        subprocess.run([compiler,"-std=c++17","-pthread",*flags,
                        "-I",str(root / "melonDS-android-lib/src"),"-I",str(root / "melonDS-android-lib/src/android"),
                        str(root / "app/src/test/cpp/SaveManagerTest.cpp"),str(root / "melonDS-android-lib/src/android/SaveManager.cpp"),
                        "-o",str(binary)],check=True,timeout=120)
        print(f"PROFILE: {profile}",flush=True)
        subprocess.run([str(binary)],check=True,timeout=15)
