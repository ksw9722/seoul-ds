#!/usr/bin/env python3
"""Destructive-to-test-data UI smoke for a disposable Android emulator only.

No ROM, BIOS dump, account, physical device, or game compatibility test is used.
Run after installing a debug x86_64 APK; adb and emulator must share a host/network.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

PACKAGE = "io.github.seoulds.emulator.dev"
ACTIVITY = f"{PACKAGE}/me.magnum.melonds.ui.romlist.RomListActivity"

class Smoke:
    def __init__(self, args):
        self.args = args
        self.out = args.output.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.results = []
        self.target_verified = False
        self.original_rotation = None
        self.original_auto_rotation = None

    def adb(self, *args, binary=False, timeout=90):
        p = subprocess.run([self.args.adb, "-s", self.args.serial, *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if p.returncode:
            raise RuntimeError(f"adb {' '.join(args[:4])} failed: {p.stderr.decode(errors='replace')}")
        return p.stdout if binary else p.stdout.decode(errors="replace")

    def dump(self):
        # A named shared temporary document is test-owned, never user storage.
        self.adb("shell", "uiautomator", "dump", "/sdcard/seoul-ui-smoke.xml")
        raw = self.adb("exec-out", "cat", "/sdcard/seoul-ui-smoke.xml")
        return ET.fromstring(raw)

    def find(self, phrases, attempts=6, scroll=False):
        if isinstance(phrases, str): phrases = [phrases]
        for _ in range(attempts):
            tree = self.dump()
            for node in tree.iter("node"):
                if any(p in node.get("text", "") or p == node.get("content-desc", "") for p in phrases):
                    return node
            if scroll:
                self.adb("shell", "input", "swipe", "360", "1090", "360", "330", "450")
            time.sleep(1)
        raise AssertionError(f"UI text not found: {phrases}")

    def tap(self, node):
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.attrib["bounds"]))
        self.adb("shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2))
        time.sleep(1)

    def click(self, phrases, scroll=False):
        self.tap(self.find(phrases, scroll=scroll))

    def back(self):
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)

    def launch(self):
        self.adb("shell", "am", "force-stop", PACKAGE)
        self.adb("shell", "am", "start", "-W", "-n", ACTIVITY, timeout=120)
        time.sleep(2)

    def snapshot(self, name):
        (self.out / f"{name}.png").write_bytes(self.adb("exec-out", "screencap", "-p", binary=True))
        (self.out / f"{name}.xml").write_bytes(ET.tostring(self.dump(), encoding="utf-8"))

    def record(self, name):
        self.results.append({"name": name, "status": "PASS"})
        print(f"PASS {name}", flush=True)

    def run(self):
        if self.adb("shell", "getprop", "ro.kernel.qemu").strip() != "1":
            raise RuntimeError("Refusing to clear data: target is not an Android emulator")
        self.target_verified = True
        self.original_rotation = self.adb("shell", "settings", "get", "system", "user_rotation").strip()
        self.original_auto_rotation = self.adb("shell", "settings", "get", "system", "accelerometer_rotation").strip()
        self.adb("shell", "pm", "path", PACKAGE)
        self.adb("shell", "pm", "clear", PACKAGE)
        self.adb("logcat", "-c")
        self.launch()
        self.find("Seoul DS에 오신 것을 환영해요")
        self.snapshot("01-first-run")
        self.record("fresh launch shows Korean guide")
        self.back()
        self.find("Seoul DS")
        self.launch()
        self.find("Seoul DS에 오신 것을 환영해요")
        self.record("Back does not complete first-run guide")
        self.click("게임 폴더 설정 열기", scroll=True)
        self.click(["ROM 검색 디렉터리", "ROM search directories", "ROM search directory"])
        # The picker is system-owned; assert its activity, then cancel without picking.
        activities = self.adb("shell", "dumpsys", "activity", "activities")
        if not any(s in activities for s in ("DocumentsActivity", "documentsui")):
            raise AssertionError("System document picker did not open")
        self.back()
        self.back()
        self.find("아직 게임 폴더를 지정하지 않았어요", scroll=True)
        self.record("document tree picker cancel preserves empty configuration")
        self.adb("shell", "settings", "put", "system", "accelerometer_rotation", "0")
        self.adb("shell", "settings", "put", "system", "user_rotation", "1")
        time.sleep(2)
        self.find("시작 안내 · 상태")
        self.snapshot("02-landscape")
        self.adb("shell", "settings", "put", "system", "user_rotation", "0")
        time.sleep(2)
        self.record("rotation keeps the guide accessible")
        self.click("GNU GPL v3 전문", scroll=True)
        self.find("GNU GENERAL PUBLIC LICENSE")
        self.snapshot("03-offline-license")
        self.back()
        self.find("오픈소스 · 라이선스")
        self.click("제3자 구성 요소 고지")
        self.find(["Seoul DS", "melonDS"], attempts=8)
        self.click("닫기")
        self.record("bundled license documents load and Back or Close dismisses")
        self.click("안내 확인 · 게임 목록 열기", scroll=True)
        self.launch()
        self.find("Seoul DS")
        tree = self.dump()
        if any("Seoul DS에 오신" in n.get("text", "") for n in tree.iter("node")):
            raise AssertionError("Explicit completion was not persisted")
        self.record("explicit completion persists across force-stop")
        # Toolbar overflow uses accessibility text in the current system locale.
        self.click(["More options", "옵션 더보기"])
        self.click("시작 안내 · 상태")
        self.find("Seoul DS에 오신 것을 환영해요")
        self.record("guide remains reopenable from menu")
        logs = self.adb("logcat", "-d", "-b", "crash")
        (self.out / "crash-buffer.txt").write_text(logs)
        if PACKAGE in logs or "FATAL EXCEPTION" in logs:
            raise AssertionError("Crash buffer contains an application crash")
        self.record("no application crash in tested flows")

    def report(self, error=None):
        report = {"utc": datetime.now(timezone.utc).isoformat(), "serial": self.args.serial,
                  "package": PACKAGE, "status": "FAIL" if error else "PASS",
                  "checks": self.results, "error": error,
                  "scope": "AOSP emulator setup-only UI smoke. No ROM, emulation gameplay, audio, save-file, physical S24 or commercial-game validation."}
        (self.out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", default="adb")
    p.add_argument("--serial", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--allow-clear-test-data", action="store_true", help="Required: destroys only the fork debug app data on the emulator")
    a=p.parse_args()
    if not a.allow_clear_test_data or not a.serial.startswith("emulator-"):
        p.error("Explicit --allow-clear-test-data and emulator-* serial are required")
    smoke=Smoke(a)
    try:
        smoke.run()
    except Exception as exc:
        smoke.report(str(exc)); print(f"FAIL: {exc}", flush=True); return 1
    finally:
        try:
            if smoke.target_verified:
                for key, value in (("user_rotation", smoke.original_rotation), ("accelerometer_rotation", smoke.original_auto_rotation)):
                    if value and value != "null":
                        smoke.adb("shell", "settings", "put", "system", key, value)
        except Exception:
            pass
    smoke.report(); return 0

if __name__ == "__main__": raise SystemExit(main())
