#!/usr/bin/env python3
"""Record honest, repeatable source/Android checks with per-command evidence."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ANDROID_TASKS = [
    ("jvm-unit-tests", ":app:testGitHubProdDebugUnitTest"),
    ("android-lint", ":app:lintGitHubProdDebug"),
    ("debug-apk", ":app:assembleGitHubProdDebug"),
]

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def capture(*command: str) -> str:
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"UNAVAILABLE: {exc}"

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()

def overall_status(checks: list[dict]) -> str:
    if any(c["status"] == "FAIL" for c in checks):
        return "FAIL"
    if any(c["status"] == "BLOCKED" for c in checks):
        return "BLOCKED"
    if any(c["status"] == "PENDING" for c in checks):
        return "INCOMPLETE"
    return "PASS"

def android_preflight(env: dict[str, str], root: Path = ROOT) -> list[str]:
    issues = []
    if env.get("ANDROID_SDK_LICENSE_ACCEPTED") != "true":
        issues.append("Set ANDROID_SDK_LICENSE_ACCEPTED=true only after explicit Android SDK/NDK terms agreement; harness never accepts licenses")
    sdk_value = env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT")
    if not sdk_value:
        issues.append("Set ANDROID_HOME to the installed SDK directory")
    else:
        sdk = Path(sdk_value)
        for relative in ("platforms/android-36/android.jar", "ndk/28.0.13004108/source.properties", "cmake/3.22.1/bin/cmake", "build-tools/36.0.0/aapt", "build-tools/36.0.0/apksigner", "build-tools/36.0.0/zipalign"):
            if not (sdk / relative).is_file():
                issues.append(f"Missing Android tool component: {relative}")
        if not any((sdk / "licenses").glob("*")):
            issues.append("SDK licenses directory is empty; use official SDK tooling after agreement")
    for binary in ("java", "javac"):
        executable = str(Path(env["JAVA_HOME"]) / "bin" / binary) if env.get("JAVA_HOME") else shutil.which(binary, path=env.get("PATH"))
        if not executable or not Path(executable).is_file():
            issues.append(f"Java 21 JDK tool {binary} not found (a JRE alone is insufficient)")
            continue
        result = subprocess.run([executable, "-version"], capture_output=True, text=True, env=env)
        version_text = result.stderr + result.stdout
        pattern = r'version "21(?:\.|\")' if binary == "java" else r'javac 21(?:\.|\s|$)'
        if result.returncode or not re.search(pattern, version_text):
            issues.append(f"Java 21 {binary} is required by the pinned project")
    if not (root / "gradlew").is_file():
        issues.append("Gradle Wrapper missing")
    return issues

def run_command(name: str, command: list[str], output: Path, env: dict[str, str], timeout: int) -> dict:
    start = time.monotonic()
    log = output / f"{name}.log"
    result = {"name": name, "command": command, "started_at": utc_now(), "log": log.name}
    print(f"RUN     {name}: {' '.join(command)}", flush=True)
    try:
        with log.open("w") as stream:
            stream.write(f"UTC: {result['started_at']}\nCOMMAND: {' '.join(command)}\n\n")
            stream.flush()
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                proc.wait(timeout=timeout)
            except BaseException:
                # Stop only this command's newly created process group; never
                # kill unrelated Java/Gradle processes belonging to the user.
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
                raise
        result.update(status=("PASS" if proc.returncode == 0 else "BLOCKED" if name == "native-host-tests" and proc.returncode == 2 else "FAIL"), exit_code=proc.returncode)
    except subprocess.TimeoutExpired:
        result.update(status="FAIL", exit_code=None, timed_out=True, reason=f"Command exceeded explicit {timeout}s timeout; launched process group stopped; no pass inferred")
    except OSError as exc:
        result.update(status="BLOCKED", exit_code=None, reason=str(exc))
    result["duration_seconds"] = round(time.monotonic() - start, 3)
    print(f"{result['status']:7} {name} ({result['duration_seconds']}s)", flush=True)
    return result

def write_report(report: dict, output: Path, completed: bool = False):
    if completed:
        report["finished_at"] = utc_now()
        report["status"] = overall_status(report["checks"])
    else:
        report.pop("finished_at", None)
        report["status"] = "RUNNING"
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = ["# Seoul DS harness", "", f"- Status: **{report['status']}**", f"- Scope: `{report['mode']}`", f"- Commit: `{report['git_commit']}`", f"- UTC: {report['started_at']}", "", "| Check | Status | Evidence |", "|---|---|---|"]
    for c in report["checks"]:
        detail = c.get("log", c.get("reason", ""))
        lines.append(f"| {c['name']} | {c['status']} | {str(detail).replace('|', '/')} |")
    lines.extend(["", "Device/emulation/game compatibility tests: **NOT RUN by this harness**.", "A successful build is not proof of Galaxy S24 or any commercial game's compatibility.", ""])
    (output / "summary.md").write_text("\n".join(lines))

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("static", "android"), default="static")
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64", "armeabi-v7a"), default="arm64-v8a")
    parser.add_argument("--optimized-native", action="store_true", help="Request and verify RelWithDebInfo optimized native core in the debug-signed APK")
    parser.add_argument("--native-build-dir", type=Path, help="Explicit optimized CMake graph if auto-selection is ambiguous")
    parser.add_argument("--output", type=Path, help="New evidence directory (must not exist)")
    parser.add_argument("--timeout", type=int, default=3600, help="Per-command timeout in seconds")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = args.output.resolve() if args.output else ROOT / "artifacts/harness" / stamp
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("GRADLE_USER_HOME", str(ROOT.parent / ".gradle-seoul-ds"))
    report = {
        "schema": 1, "mode": args.mode, "abi": args.abi, "optimized_native_requested": args.optimized_native, "started_at": utc_now(),
        "git_commit": capture("git", "rev-parse", "HEAD"),
        "git_worktree": capture("git", "status", "--short"),
        "submodules": capture("git", "submodule", "status", "--recursive"),
        "host": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version(), "java": capture("java", "-version")},
        "scope_note": "Static checks/JVM tests/lint/APK build only; no phone, emulator or ROM is launched", "checks": [], "artifacts": [],
    }
    static_tasks = [
        ("harness-self-tests", [sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests", "-v"]),
        ("source-audit", [sys.executable, "scripts/audit_source.py", "--json", str(output / "source-audit.json")]),
        ("native-host-tests", [sys.executable, "scripts/native_host_tests.py"]),
    ]
    report["checks"] = [{"name": name, "status": "PENDING"} for name, _ in static_tasks]
    report["checks"].extend({"name": name, "status": "PENDING" if args.mode == "android" else "NOT RUN", "reason": "Awaiting Android checks" if args.mode == "android" else "Static mode; select --mode android for SDK-backed checks"} for name, _ in ANDROID_TASKS)
    report["checks"].append({"name": "optimized-native-proof", "status": "PENDING" if args.mode == "android" and args.optimized_native else "NOT RUN", "reason": "Actual cache/flags/Ninja and APK build-ID proof required" if args.optimized_native else "Unoptimized developer build requested"})
    report["checks"].append({"name": "apk-validation", "status": "PENDING" if args.mode == "android" else "NOT RUN", "reason": "Requires successful APK build"})
    report["checks"].append({"name": "s24-and-game-runtime", "status": "NOT RUN", "reason": "Requires authorized physical device and lawfully supplied test content; see manual checklist"})
    def update_check(result):
        index = next(i for i, check in enumerate(report["checks"]) if check["name"] == result["name"])
        report["checks"][index] = result
    write_report(report, output)
    for name, command in static_tasks:
        update_check(run_command(name, command, output, env, args.timeout))
        write_report(report, output)
    if args.mode == "android":
        blockers = android_preflight(env)
        if any(c["status"] in {"FAIL", "BLOCKED"} for c in report["checks"]):
            blockers.append("Source/harness gate failed; fix before building")
        if blockers:
            for name in [name for name, _ in ANDROID_TASKS] + ["apk-validation"] + (["optimized-native-proof"] if args.optimized_native else []):
                update_check({"name": name, "status": "BLOCKED", "reason": "; ".join(blockers)})
        else:
            previous_timeout = False
            for name, task in ANDROID_TASKS:
                if previous_timeout:
                    update_check({"name": name, "status": "BLOCKED", "reason": "Earlier Gradle command timed out; inspect process/log state before retrying"})
                    continue
                check = run_command(name, ["bash", "./gradlew", "--no-daemon", "--console=plain", "--max-workers=1", "-Pkotlin.compiler.execution.strategy=in-process", f"-PseoulDsAbis={args.abi}", f"-PseoulDsOptimizeNative={str(args.optimized_native).lower()}", task], output, env, args.timeout)
                update_check(check)
                previous_timeout = check.get("timed_out", False)
                write_report(report, output)
            apk_check = next(c for c in report["checks"] if c["name"] == "debug-apk")
            if apk_check["status"] == "PASS":
                apks = sorted((ROOT / "app/build/outputs/apk/gitHubProd/debug").glob("*.apk"))
                if not apks:
                    apk_check.update(status="FAIL", reason="Gradle returned 0 but expected APK was not found")
                for path in apks:
                    report["artifacts"].append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path), "kind": "debug-apk", "signing": "development debug key; not production release identity"})
                if len(apks) == 1:
                    if args.optimized_native:
                        proof_command = [sys.executable, "scripts/validate_optimized_native.py", "--apk", str(apks[0]), "--abi", args.abi, "--json", str(output / "optimized-native-proof.json")]
                        if args.native_build_dir:
                            proof_command.extend(["--native-dir", str(args.native_build_dir)])
                        update_check(run_command("optimized-native-proof", proof_command, output, env, args.timeout))
                    validation = run_command("apk-validation", [sys.executable, "scripts/validate_apk.py", "--apk", str(apks[0]), "--abi", args.abi, "--json", str(output / "apk-validation.json")], output, env, args.timeout)
                    update_check(validation)
                else:
                    if args.optimized_native:
                        update_check({"name": "optimized-native-proof", "status": "BLOCKED", "reason": "Expected one freshly built APK"})
                    update_check({"name": "apk-validation", "status": "FAIL", "reason": f"Expected exactly one single-ABI APK, found {len(apks)}"})
            else:
                if args.optimized_native:
                    update_check({"name": "optimized-native-proof", "status": "BLOCKED", "reason": "APK build did not pass; no stale graph/APK inferred as optimized"})
                update_check({"name": "apk-validation", "status": "BLOCKED", "reason": "APK build did not pass; no stale APK inspected as success"})
    write_report(report, output, completed=True)
    print(f"\n{report['status']}: {output / 'report.json'}", flush=True)
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2, "INCOMPLETE": 3}[report["status"]]

if __name__ == "__main__":
    sys.exit(main())
