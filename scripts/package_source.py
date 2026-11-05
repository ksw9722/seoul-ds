#!/usr/bin/env python3
"""Create full corresponding source from a clean committed recursive or flat-vendored checkout."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]

def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE).strip()

def safe_relative(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and ".git" not in p.parts

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New .tar.gz output path; default artifacts/source/seoul-ds-<commit>-source.tar.gz")
    args = parser.parse_args()
    lock = json.loads((ROOT / "docs/upstream-lock.json").read_text())
    flat = (ROOT / "docs/publication-snapshot.json").exists()
    if flat:
        subprocess.run([sys.executable, str(ROOT / "scripts/audit_source.py")], check=True)
    repositories = [("", ROOT)]
    if not flat:
        repositories.extend((name, ROOT / name) for name in lock["submodules"])
    for prefix, repo in repositories:
        if git(repo, "status", "--porcelain", "--untracked-files=normal"):
            raise RuntimeError(f"Refusing source package from dirty/untracked tree: {prefix or 'root'}. Commit audited changes first.")
        if prefix and git(repo, "rev-parse", "HEAD") != lock["submodules"][prefix]:
            raise RuntimeError(f"Submodule differs from reviewed lock: {prefix}")
    commit = git(ROOT, "rev-parse", "HEAD")
    timestamp = int(git(ROOT, "show", "-s", "--format=%ct", "HEAD"))
    output = args.output.resolve() if args.output else ROOT / "artifacts/source" / f"seoul-ds-{commit[:12]}-source.tar.gz"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing package: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = {}
    for prefix, repo in repositories:
        records = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-s", "-z"]).split(b"\0")
        for record in records:
            if not record:
                continue
            metadata, name_b = record.split(b"\t", 1)
            mode, object_id, stage = metadata.decode().split()
            if mode == "160000":  # Child gitlinks are expanded independently.
                if flat:
                    raise RuntimeError("Flat publication contains an unexpected gitlink")
                continue
            if stage != "0":
                raise RuntimeError("Unmerged source tree")
            name = name_b.decode("utf-8")
            relative = f"{prefix}/{name}" if prefix else name
            if relative == "SOURCE_MANIFEST.json":
                continue  # Regenerate inventory; never hash an obsolete copy of itself.
            if not safe_relative(relative):
                raise RuntimeError(f"Unsafe archive path: {relative}")
            data = subprocess.check_output(["git", "-C", str(repo), "cat-file", "blob", object_id])
            if mode == "120000":
                target = data.decode("utf-8")
                if target.startswith("/") or ".." in PurePosixPath(target).parts:
                    raise RuntimeError(f"Review external/traversing source symlink: {relative}")
            entries[relative] = (mode, data)
    manifest = {
        "schema": 1, "root_commit": commit, "source_date_epoch": timestamp,
        "upstream": lock["upstream"], "submodules": lock["submodules"],
        "scope": "Full committed tracked source, expanded recursive submodules; no Git history, SDK, private keys or build cache",
        "files": [{"path": name, "mode": mode, "bytes": len(data), "sha256": digest(data)} for name, (mode, data) in sorted(entries.items())],
    }
    if flat:
        manifest["layout"] = "flat-vendored"
        manifest["original_source_commit"] = json.loads((ROOT / "docs/publication-snapshot.json").read_text())["original_source_commit"]
    entries["SOURCE_MANIFEST.json"] = ("100644", (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode())
    archive_root = f"seoul-ds-{commit[:12]}"
    try:
        with output.open("xb") as file:
            with gzip.GzipFile(filename="", mode="wb", fileobj=file, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for name, (mode, data) in sorted(entries.items()):
                        info = tarfile.TarInfo(f"{archive_root}/{name}")
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = timestamp
                        info.mode = 0o755 if mode == "100755" else 0o644
                        if mode == "120000":
                            info.type = tarfile.SYMTYPE
                            info.linkname = data.decode()
                            archive.addfile(info)
                        else:
                            info.size = len(data)
                            archive.addfile(info, io.BytesIO(data))
    except Exception:
        output.unlink(missing_ok=True)
        raise
    sha = hashlib.sha256()
    with output.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    checksum = f"{sha.hexdigest()}  {output.name}\n"
    output.with_suffix(output.suffix + ".sha256").write_text(checksum)
    print(f"PASS: {output}\nFiles: {len(manifest['files'])}\nCommit: {commit}\nSHA-256: {sha.hexdigest()}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
