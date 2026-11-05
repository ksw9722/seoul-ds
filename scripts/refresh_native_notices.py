#!/usr/bin/env python3
"""Refresh verbatim native notices from pinned corresponding source only."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MARKER = "\n\n=== RESOLVED ANDROID/JVM RUNTIME DEPENDENCY NOTICES ===\n"
FILES = [
    ("melonDS Android / Seoul DS", "LICENSE"),
    ("melonDS native core (GPL-3.0-or-later in source headers)", "melonDS-android-lib/LICENSE"),
    ("FreeBIOS replacement by Gilead Kutnick; not Nintendo BIOS", "melonDS-android-lib/freebios/drastic_bios_readme.txt"),
    ("FAAD2 — Code from FAAD2 is copyright (c) Nero AG, www.nero.com; source headers allow GPL-2.0-or-later", "melonDS-android-lib/src/android/faad2/COPYING"),
    ("Oboe", "melonDS-android-lib/src/android/oboe/LICENSE"),
    ("RetroAchievements rcheevos", "melonDS-android-lib/src/android/rcheevos/LICENSE"),
    ("Teakra", "melonDS-android-lib/src/teakra/LICENSE"),
    ("Dolphin-derived code", "melonDS-android-lib/src/dolphin/license_dolphin.txt"),
    ("blip_buf", "melonDS-android-lib/src/blip-buf/license.txt"),
    ("FatFs", "melonDS-android-lib/src/fatfs/LICENSE.txt"),
    ("tiny-AES-c", "melonDS-android-lib/src/tiny-AES-c/unlicense.txt"),
    ("libslirp", "melonDS-android-lib/src/net/libslirp/COPYRIGHT"),
]

def main():
    notices = []
    for title, path in FILES:
        data = (ROOT / path).read_bytes()
        notices.append({"title": title, "sources": [path], "text": data.decode("utf-8", errors="replace"), "sha256": hashlib.sha256(data).hexdigest()})
    # The bundled libslirp has several separately copyrighted BSD/MIT portions
    # whose individual binary-redistribution notices are not all in COPYRIGHT.
    inline = {}
    native = ROOT / "melonDS-android-lib/src"
    folders = [
        ("libslirp", native / "net/libslirp/src"),
        ("libslirp GLib shim", native / "net/libslirp/glib"),
        ("xxHash", native / "xxhash"),
        ("SHA-1 by Steve Reid", native / "sha1"),
        ("Included libpcap headers (dynamic library itself not bundled)", native / "net/pcap"),
        ("rcheevos bundled hash implementation", native / "android/rcheevos/src/rhash"),
    ]
    for component, folder in folders:
        for file in sorted(folder.rglob("*")):
            if file.suffix not in {".c", ".h"}:
                continue
            source = file.read_text(errors="replace")
            for match in re.finditer(r"/\*.*?\*/", source, re.S):
                block = match.group()
                if not re.search(r"copyright|redistribution|permission is hereby|SPDX-License-Identifier|public domain", block, re.I):
                    continue
                digest = hashlib.sha256(block.encode()).hexdigest()
                if digest not in inline:
                    inline[digest] = {"title": component + " individual source notice", "sources": [], "text": block, "sha256": digest}
                inline[digest]["sources"].append(file.relative_to(ROOT).as_posix())
    notices.extend(inline.values())
    path = ROOT / "docs/THIRD-PARTY-NOTICES.txt"
    existing = path.read_text() if path.exists() else ""
    runtime = RUNTIME_MARKER + existing.split(RUNTIME_MARKER, 1)[1] if RUNTIME_MARKER in existing else ""
    header = """Seoul DS — third-party license notices

Android fork based on melonDS Android 2.0.1. Original copyright notices remain in corresponding source. Native notice texts below are copied verbatim from the pinned source; separate runtime module metadata and license notices follow when generated. Original license terms govern; this is not legal certification.

Source provenance: docs/upstream-lock.json. Native notice provenance: docs/native-license-index.json. Full corresponding source includes the directories listed below. No Nintendo game ROM or Nintendo BIOS dump was added by this fork. The two bundled FreeBIOS replacement binaries are independently authored and licensed below.
"""
    sections = [header]
    for notice in notices:
        sections.append("\n" + "=" * 72 + "\n" + notice["title"] + "\nSources:\n" + "\n".join(notice["sources"]) + "\nSHA-256: " + notice["sha256"] + "\n" + "=" * 72 + "\n" + notice["text"])
    path.write_text("\n".join(sections) + runtime)
    index = {"scope": "Verbatim named native license files and distinct inline bundled-component notices", "entries": [{k: v for k, v in item.items() if k != "text"} for item in notices]}
    (ROOT / "docs/native-license-index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    print(f"PASS: {len(FILES)} complete native license files and {len(inline)} distinct inline bundled-component notices")

if __name__ == "__main__":
    main()
