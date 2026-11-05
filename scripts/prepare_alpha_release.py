#!/usr/bin/env python3
"""Prepare public alpha assets only from this commit's passing Android harness."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CHECKS = {'harness-self-tests', 'source-audit', 'native-host-tests', 'jvm-unit-tests', 'android-lint', 'debug-apk', 'optimized-native-proof', 'apk-validation'}

def validate_report(report, commit):
    if report.get('status') != 'PASS' or report.get('mode') != 'android':
        raise ValueError('A passing Android harness report is required')
    if report.get('git_commit') != commit or report.get('git_worktree'):
        raise ValueError('Report must match this clean source commit')
    if report.get('abi') != 'arm64-v8a' or report.get('optimized_native_requested') is not True:
        raise ValueError('Optimized ARM64 evidence is required')
    checks = {check['name']: check['status'] for check in report.get('checks', [])}
    if any(checks.get(name) != 'PASS' for name in REQUIRED_CHECKS):
        raise ValueError('Required Android checks did not all pass')
    if checks.get('s24-and-game-runtime') != 'NOT RUN':
        raise ValueError('Unexpected device-runtime claim: review before release')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'alpha-[A-Za-z0-9._-]+', args.tag):
        raise ValueError('Only alpha tags are supported')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    report = json.loads(args.report.read_text())
    validate_report(report, commit)
    apks = list((ROOT / 'app/build/outputs/apk/gitHubProd/debug').glob('*.apk'))
    if len(apks) != 1:
        raise ValueError('Expected exactly one freshly built APK')
    # Match the APK digest recorded by the completed harness, not a later replacement.
    apk_hash = hashlib.sha256(apks[0].read_bytes()).hexdigest()
    if not any(a.get('sha256') == apk_hash for a in report.get('artifacts', [])):
        raise ValueError('APK does not match the passing harness artifact')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / f'seoul-ds-{commit[:12]}-source.tar.gz'
    subprocess.run([sys.executable, str(ROOT / 'scripts/package_source.py'), '--output', str(source)], check=True)
    shutil.copy2(apks[0], output / f'seoul-ds-{commit[:12]}-arm64-development.apk')
    shutil.copy2(ROOT / 'docs/THIRD-PARTY-NOTICES.txt', output / 'THIRD-PARTY-NOTICES.txt')
    shutil.copy2(ROOT / 'LICENSE', output / 'LICENSE.txt')
    shutil.copy2(args.report, output / 'verification-report.json')
    shutil.copy2(args.report.parent / 'summary.md', output / 'verification-summary.md')
    with tarfile.open(output / 'verification-evidence.tar.gz', 'w:gz') as archive:
        archive.add(args.report.parent, arcname='android-verification')
    (output / 'release-metadata.json').write_text(json.dumps({'schema': 1, 'tag': args.tag, 'source_commit': commit, 'apk_sha256': apk_hash, 'signing': 'ephemeral Android debug key; not stable release signing', 's24_runtime': 'NOT RUN'}, indent=2) + '\n')
    (output / 'RELEASE-NOTES.md').write_text(f'''# Seoul DS development alpha

Source commit: `{commit}`. Full corresponding source, licenses, notices, checksums and verification evidence are attached to this same release.

This is an **ARM64 optimized native development APK**, application ID `io.github.seoulds.emulator.dev`, built with Java 21, SDK 36, NDK 28.0.13004108, CMake 3.22.1 and Gradle 9.1.0. Static checks, JVM tests, lint, APK signature/alignment and optimized-native evidence passed. Translation lint debt remains documented in the source.

**Signing:** the fresh runner generates an ephemeral Android debug signing key. This is not stable release signing and is not suitable for a production update channel. Different runs can have different signing certificates, so installing over a previous build may fail. Back up/export saves before any uninstall; uninstalling can remove app data. No signing key is published or persisted.

**Not tested:** Galaxy S24 runtime, commercial-game compatibility and device save stability. A successful build is not a device compatibility claim. No games or proprietary BIOS are included. Use only legally obtained content.

Verify downloads with `sha256sum --check SHA256SUMS.txt` after downloading all assets. Rebuild instructions and source provenance are included in the source archive under `README.md` and `docs/`.
''')
    sums = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}' for p in sorted(output.iterdir()) if p.is_file()]
    (output / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n')
    print(f'Prepared alpha bundle for {commit}: {output}')

if __name__ == '__main__':
    main()
