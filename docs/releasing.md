# 공개 배포 게이트

소스 공개와 APK 릴리스는 별도 단계입니다. 사용자는 공개 GitHub 저장소 생성을 요청했지만, 이 문서는 실제 게시가 완료되었다는 의미가 아닙니다. 배포 담당자가 대상 계정/저장소와 공개 상태를 확인하고 원격 커밋 및 해당 커밋의 CI를 검증합니다.

## 소스 공개 전

- [ ] 최종 소스 diff 리뷰: 새 안내/저장 안전성/브랜딩/업데이트 경로가 서로 일치.
- [ ] `python3 scripts/harness.py --mode static` 통과, 결과/커밋 기록.
- [ ] LICENSE, 원작 고지, 하위 모듈 정확한 pin, 전체 서드파티 고지 유지.
- [ ] ROM/독점 BIOS/게임 화면·표지/세이브/키/토큰/개인 경로/빌드 캐시 제외.
- [ ] **전체 Git history**도 감사. 원작 history의 게임 이미지가 불명확하면 감사한 현행 소스의 새 Git 이력과 upstream provenance를 사용.
- [ ] 새 repo `origin`이 사용자 소유 대상인지 확인. 원작 remote에 push하지 않음.
- [ ] README·업데이트·이슈·펀딩 링크에서 원작 공식 배포로 오인시키는 표현 없음.

## APK 배포 전

- [ ] 해당 커밋에서 `--optimized-native` Android 하네스 단위 테스트/Lint/ARM64 빌드 통과. 실제 RelWithDebInfo cache/유효 flags와 완료된 Ninja graph·APK/ELF GNU build ID 일치 증거 포함.
- [ ] 실제 APK ID `io.github.seoulds.emulator.dev`, ARM64 native library, SDK 값, 서명 검증, SHA-256 기록. 64비트 ELF LOAD16KiB 및 `zipalign -c -P 16 4` 패키징 확인(실행 호환성 검증과 구분).
- [ ] 새 독립 릴리스 키가 없으면 **개인 테스트용 Debug/alpha**로 명확히 표시. 디버그 키를 저장소에 올리지 않음.
- [ ] 실행된 검사·실행되지 않은 S24/게임 호환성 테스트를 릴리스 노트에 분리.
- [ ] 상속된 PCAP/LBL 광고 조항 위험 확인: Android 바이너리에서 해당 백엔드/헤더 제외 또는 검증된 별도 근거. 단순 고지 추가만으로 호환 문제 해결을 주장하지 않음.
- [ ] 실제 runtimeClasspath의 POM/AAR/JAR과 Native 라이선스/NOTICE 검토 및 필요한 고지를 APK·배포 자료에 포함.
- [ ] APK의 정확한 수정 소스와 빌드 방법을 같은 다운로드 위치에서 제공. 상류 소스 링크만으로 대체하지 않음.

## 대응 소스 묶음

작업 트리를 검토·커밋한 후 실행합니다. 하위 모듈은 GitHub 자동 ZIP에 들어가지 않으므로 아래 재귀 묶음을 별도로 제공합니다.

```bash
python3 scripts/package_source.py
# artifacts/source/seoul-ds-<commit>-source.tar.gz 및 .sha256 생성
```

패키저는 커밋된 파일과 모든 하위 모듈의 Git 객체를 읽고 각 파일 SHA-256/커밋을 `SOURCE_MANIFEST.json`에 기록합니다. dirty/untracked tree, 예상과 다른 submodule pin, 위험 archive 경로는 거부합니다. Git history·SDK/NDK·키·캐시를 포함하지 않습니다. 같은 소스 커밋·하위 모듈이면 재현 가능한 tar/gzip 메타데이터를 사용합니다.

압축을 새 폴더에 풀어 다음을 확인합니다.

```bash
python3 scripts/audit_source.py
python3 -m unittest discover -s scripts/tests -v
# 허가·SDK가 있는 환경에서는 동일 Gradle 빌드를 재검사
```

APK, 대응 소스 `.tar.gz`, 각각의 SHA-256, 전체 `THIRD-PARTY-NOTICES.txt`, 검증 요약을 함께 배포합니다. 정식 릴리스 서명/업데이트 정책·실기기 검증이 미완료이면 안정 버전이라고 표시하지 않습니다.

## Flat public snapshot

The public repository vendors the expanded modules as ordinary files. No recursive submodule download is needed. The packager reads the clean root Git checkout, verifies vendored hashes against the original inventory, and generates a fresh SOURCE_MANIFEST.json (excluding itself). See [published-snapshot.md](published-snapshot.md) for provenance and verification limits. The earlier recursive-checkout instructions apply only to the original development checkout.

## GitHub Actions alpha prerelease

The `alpha-release.yml` workflow publishes only development **prereleases**, never a stable/latest release. Run **Seoul DS alpha APK prerelease** manually on the default branch, setting `accept_android_sdk_terms=true` only after accepting [Android SDK/NDK terms](https://developer.android.com/studio/terms). A previously recorded explicit acceptance covers this input; it is an automation gate, not a demand to accept again. Alternatively, push an `alpha-*` tag after recording `ANDROID_SDK_LICENSE_ACCEPTED=true` as a repository variable. Missing consent skips the build and publishes nothing. Ordinary branch pushes and pull requests do not publish APKs.

The read-only build job runs source checks, installs pinned tools, runs the Android harness (JVM tests, lint, ARM64 optimized build, APK/signature/alignment/native-graph checks), then packages full corresponding source from that exact clean commit. A separate publish job receives only this run's immutable artifact, checks commit identity and SHA-256, and gets `contents: write` plus `actions: read`. It does not check out or execute repository code. No personal token, persistent signing key or new secret is required. All actions are SHA-pinned. The source audit pins the exact reviewed release-workflow digest; intentional workflow changes must update that pin after review.

Manual runs generate a unique `alpha-<short-commit>-<run-id>-<attempt>` tag. Tag-triggered runs retain the requested tag. Assets are first attached to a draft, then the complete release is made public as a prerelease and explicitly not marked latest. Existing releases are never overwritten. If upload fails, inspect the draft before retrying; a failed run is not evidence of publication. A rerun for an already published tag will fail rather than mutate it. Tags created with this workflow's scoped `GITHUB_TOKEN` do not recursively start another release workflow.

Assets: optimized ARM64 `.dev` debug APK; full corresponding source archive and checksum; `SHA256SUMS.txt`; full notices and GPL license; exact-commit metadata; release notes; verification report, summary and detailed evidence. Verify all downloads using `sha256sum --check SHA256SUMS.txt`. The source archive contains build instructions and the original provenance.

**Signing and compatibility:** the isolated fresh runner creates a new ephemeral Android debug key. It is not saved to GitHub, cached, uploaded or reused. This is not production signing. APKs from different runs can have incompatible certificates, so an in-place update may fail. Export/back up saves before uninstalling anything; uninstalling can erase app data. Stable release signing and its secure custody require a separate explicit setup. Galaxy S24 runtime, game compatibility and device save stability remain untested; no build result substitutes for those tests.

The pipeline itself must pass on the public commit before claiming an APK is available. Local static workflow checks do not mean an Android build or public release has completed.
