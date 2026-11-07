#!/usr/bin/env python3
"""Offline, conservative source checks; not a malware or copyright guarantee."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Exact reviewed opt-in alpha pipeline; changes require an explicit policy review.
APPROVED_ALPHA_WORKFLOW_SHA256 = "8769a85b2d83c77b65984f61098c63673219e28b692e4fd0aa1f93b69695d730"
FREEBIOS = {
    "melonDS-android-lib/freebios/drastic_bios_arm7.bin": "80ae613b1cfd4cd56dd49f9e985b9788563388facaf0d0f5f78ea2b185f3f7c5",
    "melonDS-android-lib/freebios/drastic_bios_arm9.bin": "39b4a574f4a24465fa4c7c9d2d4c847fdd46133b54528a22a7e198fe3a37e281",
}
# Never emit the matched secret value into logs.
SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Google API key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
}
LEGACY_BRANDING = {
    "app/src/main/res/drawable/logo_dsiware.png",
    "app/src/main/res/drawable-night/logo_dsiware.png",
    "app/src/main/res/drawable/ic_melon_small.png",
    "app/src/main/ic_launcher-web.png",
}
PROHIBITED_EXTENSIONS = {".nds", ".srl", ".gba", ".gb", ".gbc", ".cia", ".3ds", ".sav", ".dsv", ".jks", ".keystore", ".p12", ".pfx"}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE).strip()

def inventory(root: Path) -> list[Path]:
    """Git-tracked + not-ignored working source, recursively, or packaged manifest."""
    if not (root / ".git").exists():
        manifest = json.loads((root / "SOURCE_MANIFEST.json").read_text())
        paths = [root / record["path"] for record in manifest["files"]]
        return [p for p in paths if p.is_file()]
    repositories = [root]
    lock = json.loads((root / "docs/upstream-lock.json").read_text())
    if not (root / "docs/publication-snapshot.json").exists():
        repositories.extend(root / p for p in lock["submodules"])
    result = set()
    for repo in repositories:
        output = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard"])
        for raw in output.split(b"\0"):
            if raw:
                p = repo / raw.decode("utf-8")
                if p.is_file():
                    result.add(p)
    return sorted(result)

def verify_vendored_provenance(root: Path, files: list[Path]) -> None:
    """Verify flat vendored code against the preserved original source inventory."""
    publication = json.loads((root / "docs/publication-snapshot.json").read_text())
    if publication.get("layout") != "flat-vendored":
        raise AssertionError("Unknown publication source layout")
    original_path = root / "docs/original-source-manifest.json"
    if sha256(original_path) != publication["original_manifest_sha256"]:
        raise AssertionError("Original source manifest hash mismatch")
    original = json.loads(original_path.read_text())
    lock = json.loads((root / "docs/upstream-lock.json").read_text())
    if original["root_commit"] != publication["original_source_commit"] or original["submodules"] != lock["submodules"] or original["upstream"] != lock["upstream"]:
        raise AssertionError("Original source identity or upstream provenance differs from lock")
    def vendored(name):
        return any(name.startswith(module + "/") for module in lock["submodules"])
    expected = {record["path"]: record for record in original["files"] if vendored(record["path"])}
    # Keep the upstream inventory immutable. Each local fork edit needs explicit old/new
    # hashes and a human-readable reason; absent or stale records still fail closed.
    modifications = root / "docs/native-modifications.json"
    if modifications.exists():
        changes = json.loads(modifications.read_text())
        if changes.get("schema") != 1 or not isinstance(changes.get("files"), list):
            raise AssertionError("Invalid native modification provenance")
        seen = set()
        for change in changes["files"]:
            name = change.get("path", "")
            if name in seen or not vendored(name) or ".." in Path(name).parts or Path(name).is_absolute():
                raise AssertionError("Invalid native modification path")
            seen.add(name)
            old = expected.get(name)
            if change.get("original_sha256") != (old["sha256"] if old else None):
                raise AssertionError(f"Native modification original hash mismatch: {name}")
            digest = change.get("sha256", "")
            if not re.fullmatch(r"[0-9a-f]{64}", digest) or not change.get("reason", "").strip():
                raise AssertionError("Native modification needs hash and reason")
            expected[name] = {"path": name, "sha256": digest}
    actual = {p.relative_to(root).as_posix() for p in files if vendored(p.relative_to(root).as_posix())}
    if actual != set(expected):
        raise AssertionError("Vendored source inventory differs from original manifest")
    for name, record in expected.items():
        if sha256(root / name) != record["sha256"]:
            raise AssertionError(f"Vendored source hash mismatch: {name}")
    if (root / ".git").exists():
        stages = git(root, "ls-files", "--stage")
        if any(line.startswith("160000 ") for line in stages.splitlines()):
            raise AssertionError("Flat publication must not contain submodule gitlinks")

def forbidden_asset(path: str, data_hash: str | None = None) -> bool:
    p = Path(path)
    if path in FREEBIOS:
        return data_hash != FREEBIOS[path]
    if path.lower() in LEGACY_BRANDING:
        return True
    lower = p.name.lower()
    return (p.suffix.lower() in PROHIBITED_EXTENSIONS
            or re.fullmatch(r".*\.ml[0-9]", lower) is not None
            or (p.suffix.lower() == ".bin" and any(s in lower for s in ("bios", "firmware", "nand")))
            or lower in {"local.properties", "google-services.json"}
            or ".github/images/" in path)

def secret_kinds(data: bytes) -> list[str]:
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(data)]

def run_audit(root: Path = ROOT) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    def check(name: str, action):
        try:
            detail = action()
            results.append({"check": name, "status": "PASS", "detail": detail or "Checked"})
        except Exception as exc:
            results.append({"check": name, "status": "FAIL", "detail": str(exc)})
    def require(condition: bool, message: str):
        if not condition:
            raise AssertionError(message)
    lock = json.loads((root / "docs/upstream-lock.json").read_text())
    files = inventory(root)
    def pins():
        flat = (root / "docs/publication-snapshot.json").exists()
        if flat:
            verify_vendored_provenance(root, files)
        if (root / ".git").exists() and not flat:
            for path, expected in lock["submodules"].items():
                actual = git(root / path, "rev-parse", "HEAD")
                require(actual == expected, f"Wrong submodule pin: {path} ({actual})")
                require(not git(root / path, "status", "--porcelain", "--untracked-files=normal"), f"Dirty submodule: {path}")
            status = git(root, "submodule", "status", "--recursive")
            require(not any(line[:1] in {"-", "+", "U"} for line in status.splitlines()), "Submodule not initialized or differs from gitlink")
        elif not (root / ".git").exists():
            manifest = json.loads((root / "SOURCE_MANIFEST.json").read_text())
            require(manifest["submodules"] == lock["submodules"], "Packaged submodule manifest differs from lock")
            for record in manifest["files"]:
                p = root / record["path"]
                require(p.is_file() and sha256(p) == record["sha256"], f"Packaged source hash mismatch: {record['path']}")
        return f"{len(lock['submodules'])} modules: " + ("flat vendored hashes and original provenance verified" if flat else "recursive pins verified")
    check("upstream-pins", pins)
    def license_files():
        paths = ["LICENSE", "melonDS-android-lib/LICENSE", "melonDS-android-lib/src/android/faad2/COPYING", "melonDS-android-lib/src/android/oboe/LICENSE", "melonDS-android-lib/freebios/drastic_bios_readme.txt", "docs/third-party-notices.md"]
        for path in paths:
            require((root / path).is_file() and (root / path).stat().st_size > 100, f"Missing license: {path}")
        require("GNU GENERAL PUBLIC LICENSE" in (root / "LICENSE").read_text(), "Root GPL license missing")
        return f"{len(paths)} required root/native notices present; runtime inventory checked separately"
    check("required-licenses", license_files)
    def packaged_notices():
        copies = [("LICENSE", "app/src/main/assets/licenses/GPL-3.0.txt"), ("docs/THIRD-PARTY-NOTICES.txt", "app/src/main/assets/licenses/THIRD-PARTY-NOTICES.txt")]
        for source, asset in copies:
            require((root / asset).is_file(), f"Missing APK license asset: {asset}")
            require((root / source).read_bytes() == (root / asset).read_bytes(), f"APK notice differs from source notice: {asset}")
        for index in ("docs/native-license-index.json", "docs/runtime-dependencies.json"):
            require((root / index).is_file(), f"Missing release license evidence: {index}")
        runtime = json.loads((root / "docs/runtime-dependencies.json").read_text())
        require(not runtime.get("errors"), "Unresolved runtime dependency license metadata")
        require(runtime.get("module_count", 0) > 0, "Empty runtime dependency inventory")
        return "APK assets match complete source license notices; native/runtime evidence indexes present"
    check("apk-license-assets", packaged_notices)
    def xml_validity():
        xmls = [p for p in files if p.suffix == ".xml" and not p.relative_to(root).as_posix().startswith("melonDS-android-lib/")]
        for path in xmls:
            try:
                ET.parse(path)
            except ET.ParseError as exc:
                raise AssertionError(f"Invalid XML {path.relative_to(root)}: {exc}") from exc
        return f"Parsed {len(xmls)} Android XML files (syntax only)"
    check("android-xml-syntax", xml_validity)
    def localization_baseline():
        path = root / "app/lint-baseline.xml"
        require(path.is_file(), "Missing reviewed localization-only baseline")
        issues = ET.parse(path).getroot().findall("issue")
        require(len(issues) == 372, "Localization baseline count changed; explicit review required")
        require(all(item.attrib.get("id") == "MissingTranslation" for item in issues), "Baseline must never suppress non-localization defects")
        require((root / "docs/testing/lint-debt.md").is_file(), "Missing localization debt disclosure")
        return "Exactly 372 reviewed MissingTranslation records; API/runtime defects cannot be hidden here"
    check("localization-only-lint-baseline", localization_baseline)
    def branding():
        gradle = (root / "app/build.gradle.kts").read_text()
        require(re.search(r'applicationId\s*=\s*"io\.github\.seoulds\.emulator"', gradle), "Expected independent application ID")
        require('applicationIdSuffix = ".dev"' in gradle, "Missing separate debug application ID")
        require("seoulDsAbis" in gradle, "Missing documented ABI selector")
        strings = "\n".join(p.read_text() for p in (root / "app/src/main/res/values").glob("*.xml"))
        require(re.search(r'<string[^>]*name="app_name"[^>]*>Seoul DS</string>', strings), "Expected Seoul DS launcher name")
        return "Independent production/debug IDs, launcher name and ABI selector"
    check("fork-identity", branding)
    def versions():
        config = (root / "buildSrc/src/main/kotlin/AppConfig.kt").read_text()
        require(re.search(r"compileSdkVersion\s*=\s*36\b", config), "compileSdk changed from lock")
        require(re.search(r"minSdkVersion\s*=\s*24\b", config), "minSdk changed from lock")
        require('ndkVersion = "28.0.13004108"' in config, "NDK changed from lock")
        require("gradle-9.1.0-bin.zip" in (root / "gradle/wrapper/gradle-wrapper.properties").read_text(), "Gradle changed from lock")
        require('version = "3.22.1"' in (root / "app/build.gradle.kts").read_text(), "CMake changed from lock")
        return "SDK 36/min24, NDK 28.0.13004108, Gradle 9.1.0 and CMake 3.22.1"
    check("build-tool-pins", versions)
    def default_ds_boot():
        tree = ET.parse(root / "app/src/main/res/xml/pref_custom_firmware.xml")
        ns = "{http://schemas.android.com/apk/res/android}"
        defaults = {e.attrib.get(ns + "key"): e.attrib.get(ns + "defaultValue") for e in tree.iter()}
        require(defaults.get("use_custom_bios") == "false", "Custom BIOS must remain off by default")
        require(defaults.get("show_bios") == "false", "BIOS menu must remain off by default")
        require(defaults.get("console_type") == "ds", "Default console must remain DS")
        return "DS direct boot defaults preserved"
    check("ds-boot-defaults", default_ds_boot)
    def assets():
        problems = []
        for p in files:
            name = p.relative_to(root).as_posix()
            if forbidden_asset(name, sha256(p) if name in FREEBIOS else None):
                problems.append(name)
        require(not problems, "Review prohibited/private asset paths: " + ", ".join(problems[:15]))
        for path, expected in FREEBIOS.items():
            require((root / path).is_file() and sha256(root / path) == expected, f"FreeBIOS provenance mismatch: {path}")
        return f"Scanned {len(files)} source paths; two licensed FreeBIOS replacements explicitly hash-allowed"
    check("distribution-asset-paths", assets)
    def secrets():
        problems = []
        scanned = 0
        for p in files:
            if p.stat().st_size > 2 * 1024 * 1024:
                continue
            data = p.read_bytes()
            if b"\0" in data[:8192]:
                continue
            scanned += 1
            found = secret_kinds(data)
            if found:
                problems.append(f"{p.relative_to(root)}: {', '.join(found)}")
        require(not problems, "Secret-like material (values redacted): " + "; ".join(problems[:15]))
        return f"Scanned {scanned} text files for high-confidence patterns; not an exhaustive secret audit"
    check("high-confidence-secrets", secrets)
    def workflows():
        candidates = list((root / ".github/workflows").glob("*.y*ml"))
        require(bool(candidates), "Missing CI workflow")
        for p in candidates:
            text = p.read_text()
            require("contents: read" in text, f"Workflow needs read-only contents: {p.name}")
            require(not any(x in text for x in ("git push", "release-action", "upload-google-play", "pull_request_target:", "secrets.MELONDS")), f"Unsafe upstream publication workflow remains: {p.name}")
            if "contents: write" in text:
                require(p.name == "alpha-release.yml" and sha256(p) == APPROVED_ALPHA_WORKFLOW_SHA256, f"Unreviewed write-capable workflow: {p.name}")
            for action in re.findall(r"uses:\s*([^\s#]+)", text):
                require(re.search(r"@[0-9a-f]{40}$", action), f"Unpinned GitHub action: {action}")
            require("ANDROID_SDK_LICENSE_ACCEPTED" in text, f"Missing SDK consent gate: {p.name}")
        return f"{len(candidates)} workflow(s): immutable action refs; ordinary CI read-only, exact reviewed opt-in alpha release only"
    check("safe-ci-workflows", workflows)
    def docs():
        needed = ["README.upstream.md", "docs/ai-dlc/requirements.md", "docs/ai-dlc/design.md", "docs/testing/s24-device-checklist.md", "docs/testing/verification-status.md", "docs/releasing.md", "docs/privacy-ko.md"]
        for path in needed:
            require((root / path).is_file(), f"Missing documentation: {path}")
        return f"{len(needed)} required process/safety documents"
    check("ai-dlc-evidence-docs", docs)
    return results

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Write structured report")
    args = parser.parse_args()
    try:
        results = run_audit()
    except Exception as exc:
        results = [{"check": "audit-startup", "status": "FAIL", "detail": str(exc)}]
    for result in results:
        print(f"{result['status']:7} {result['check']}: {result['detail']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"scope": "offline-static-only", "checks": results}, indent=2) + "\n")
    return int(any(r["status"] != "PASS" for r in results))

if __name__ == "__main__":
    sys.exit(main())
