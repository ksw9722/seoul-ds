#!/usr/bin/env python3
"""Extract resolved runtime POM license metadata and verbatim archive notices.

Only reads supplied local Gradle resolution evidence/cache. No network, no legal
certification. Unknown/missing POM licenses are reported and fail the audit.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = "\n\n=== RESOLVED ANDROID/JVM RUNTIME DEPENDENCY NOTICES ===\n"
EXTRAS = [
    ("androidx.camera:camera-core:1.5.3", "docs/licenses/libyuv-LICENSE.txt", "https://chromium.googlesource.com/libyuv/libyuv/+/refs/heads/main/LICENSE"),
    ("org.tukaani:xz:1.11", "docs/licenses/xz-1.11-COPYING.txt", "https://raw.githubusercontent.com/tukaani-project/xz-java/v1.11/COPYING"),
    ("org.reactivestreams:reactive-streams:1.0.3", "docs/licenses/reactive-streams-1.0.3-COPYING.txt", "https://raw.githubusercontent.com/reactive-streams/reactive-streams-jvm/v1.0.3/COPYING"),
    ("io.reactivex.rxjava2:rxjava:2.2.9", "docs/licenses/rxjava-2.2.9-LICENSE.txt", "https://raw.githubusercontent.com/ReactiveX/RxJava/v2.2.9/LICENSE"),
]

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def text(node, tag):
    return node.findtext("{*}" + tag, default="")

def pom_metadata(cache: Path, group: str, name: str, version: str, seen=None):
    key = f"{group}:{name}:{version}"
    seen = set() if seen is None else seen
    if key in seen:
        return {"error": "POM parent cycle", "licenses": []}
    seen.add(key)
    poms = sorted((cache / group / name / version).glob("*/*.pom"))
    if not poms:
        return {"error": "POM not available in supplied cache", "licenses": []}
    p = poms[0]
    raw = p.read_bytes()
    root = ET.fromstring(raw)
    licenses = [{"name": text(n, "name"), "url": text(n, "url")} for n in root.findall("{*}licenses/{*}license")]
    result = {"pom_sha256": sha(raw), "project_url": text(root, "url"), "licenses": licenses, "license_source": key}
    if not licenses:
        parent = root.find("{*}parent")
        if parent is not None:
            inherited = pom_metadata(cache, text(parent, "groupId"), text(parent, "artifactId"), text(parent, "version"), seen)
            result["licenses"] = inherited.get("licenses", [])
            result["license_source"] = inherited.get("license_source", "")
            result["parent_pom_sha256"] = inherited.get("pom_sha256", "")
        if not result["licenses"]:
            result["error"] = "No declared or inherited POM license"
    return result

def archive_notices(data: bytes, origin: str, depth=0):
    result = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            name = entry.filename
            if re.search(r"(?:^|/)(?:LICENSE|NOTICE|COPYING)(?:[-_.][^/]*)?$", name, re.I) and not name.endswith(".class"):
                if entry.file_size > 2 * 1024 * 1024:
                    raise ValueError(f"Unexpectedly large license entry in {origin}")
                raw = archive.read(entry)
                result.append({"source": f"{origin}!/{name}", "sha256": sha(raw), "text": raw.decode("utf-8", errors="replace")})
            elif depth < 1 and name.endswith(".jar") and entry.file_size < 100 * 1024 * 1024:
                result.extend(archive_notices(archive.read(entry), f"{origin}!/{name}", depth + 1))
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True, help="Gradle caches/modules-2/files-2.1")
    parser.add_argument("--write", action="store_true", help="Refresh docs inventory and runtime notice section")
    args = parser.parse_args()
    evidence = json.loads(args.inventory.read_text())
    artifacts = {a["id"]: Path(a["file"]) for a in evidence["artifacts"]}
    modules = []
    collected = []
    errors = []
    for module in sorted(evidence["modules"], key=lambda m: (m["group"], m["name"], m["version"])):
        coordinate = ":".join(module[k] for k in ("group", "name", "version"))
        metadata = pom_metadata(args.cache, module["group"], module["name"], module["version"])
        row = {"coordinate": coordinate, **metadata, "artifacts": [], "embedded_notices": []}
        if metadata.get("error"):
            errors.append(f"{coordinate}: {metadata['error']}")
        artifact = artifacts.get(coordinate)
        if artifact:
            if not artifact.is_file():
                errors.append(f"Missing resolved artifact: {coordinate}")
            else:
                raw = artifact.read_bytes()
                row["artifacts"].append({"name": artifact.name, "sha256": sha(raw), "bytes": len(raw)})
                if artifact.suffix in {".jar", ".aar"}:
                    notices = archive_notices(raw, f"{coordinate}/{artifact.name}")
                    collected.extend(notices)
                    row["embedded_notices"] = [{k: v for k, v in n.items() if k != "text"} for n in notices]
        modules.append(row)
    coords = {m["coordinate"] for m in modules}
    extra_meta = []
    for coordinate, path, url in EXTRAS:
        if coordinate in coords:
            p = ROOT / path
            if not p.is_file():
                errors.append(f"Missing supplemental license: {path}")
                continue
            raw = p.read_bytes()
            item = {"source": url, "sha256": sha(raw), "text": raw.decode()}
            collected.append(item)
            extra_meta.append({"coordinate": coordinate, "path": path, "source": url, "sha256": sha(raw)})
    unique = {}
    for notice in collected:
        if notice["sha256"] not in unique:
            unique[notice["sha256"]] = {"text": notice["text"], "sources": []}
        unique[notice["sha256"]]["sources"].append(notice["source"])
    report = {"schema": 1, "configuration": evidence["configuration"], "scope": "Resolved gitHubProdDebugRuntimeClasspath external modules; POM declared/inherited license metadata and embedded AAR/JAR notices plus pinned supplemental notices", "module_count": len(modules), "unique_notice_texts": len(unique), "errors": errors, "modules": modules, "supplemental_notices": extra_meta}
    if args.write:
        (ROOT / "docs/runtime-dependencies.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        notice_path = ROOT / "docs/THIRD-PARTY-NOTICES.txt"
        base = notice_path.read_text().split(MARKER)[0]
        sections = [base, MARKER, f"Resolved configuration: {evidence['configuration']}\nExternal modules: {len(modules)}\nThe following metadata is descriptive; original license terms govern.\n"]
        for row in modules:
            sections.append(row["coordinate"] + " — " + "; ".join(x["name"] for x in row["licenses"]) + "\n")
        for digest, notice in sorted(unique.items()):
            sections.append("\n" + "=" * 72 + "\nSHA-256: " + digest + "\nSources:\n" + "\n".join(notice["sources"]) + "\n" + "=" * 72 + "\n" + notice["text"] + "\n")
        notice_path.write_text("\n".join(sections))
    print(f"{'FAIL' if errors else 'PASS'}: {len(modules)} runtime modules, {len(collected)} notice entries, {len(unique)} distinct full texts")
    for error in errors:
        print(error)
    return int(bool(errors))

if __name__ == "__main__":
    sys.exit(main())
