"""Harness correctness tests with synthetic data; never ship game fixtures."""
import importlib.util
import json
import io
import zipfile
import subprocess
import os
import sys
import tarfile
import struct
from unittest.mock import patch
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

audit = load("audit_source")
harness = load("harness")
packaging = load("package_source")
notices = load("collect_dependency_notices")
apk_validation = load("validate_apk")
native_proof = load("validate_optimized_native")

class SourcePolicyTests(unittest.TestCase):
    def test_disallows_rom_case_insensitively(self):
        self.assertTrue(audit.forbidden_asset("app/src/main/assets/game.NDS"))

    def test_legacy_brand_art_cannot_return(self):
        for path in audit.LEGACY_BRANDING:
            self.assertTrue(audit.forbidden_asset(path), path)
        self.assertFalse(audit.forbidden_asset("app/src/main/res/drawable/logo_dsiware.xml"))
        self.assertFalse(audit.forbidden_asset("app/src/main/res/drawable/ic_melon_small.xml"))

    def test_disallows_user_save(self):
        for name in ("progress.sav", "progress.dsv", "quick.ml0"):
            self.assertTrue(audit.forbidden_asset(name), name)

    def test_disallows_keystore_and_local_configuration(self):
        for name in ("release.jks", "signing.keystore", "local.properties", "google-services.json"):
            self.assertTrue(audit.forbidden_asset(name), name)

    def test_disallows_unapproved_bios(self):
        self.assertTrue(audit.forbidden_asset("assets/bios7.bin"))
        self.assertTrue(audit.forbidden_asset("assets/firmware.bin"))

    def test_freebios_is_allowed_only_by_exact_path_and_hash(self):
        for path, digest in audit.FREEBIOS.items():
            self.assertFalse(audit.forbidden_asset(path, digest))
            self.assertTrue(audit.forbidden_asset(path, "0" * 64))
            self.assertTrue(audit.forbidden_asset(path, None))

    def test_regular_source_and_notice_allowed(self):
        self.assertFalse(audit.forbidden_asset("src/SaveState.kt"))
        self.assertFalse(audit.forbidden_asset("freebios/drastic_bios_readme.txt"))

    def test_secret_match_is_redacted(self):
        fake = ("gh" + "p_" + "a" * 36).encode()
        self.assertEqual(["GitHub token"], audit.secret_kinds(fake))
        self.assertNotIn(fake.decode(), str(audit.secret_kinds(fake)))

    def test_public_config_reference_is_not_secret(self):
        self.assertEqual([], audit.secret_kinds(b"storePassword = props[\"MELONDS_KEYSTORE_PASSWORD\"] as String?"))

    def test_private_key_header_detection(self):
        fake = b"-----BEGIN " + b"PRIVATE KEY-----"
        self.assertEqual(["private key"], audit.secret_kinds(fake))

    def test_sha256(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.txt"
            p.write_text("abc")
            self.assertEqual("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", audit.sha256(p))

class ApkValidationTests(unittest.TestCase):
    def elf_with_load_segment(self, alignment=16384, virtual_address=16384):
        data = bytearray(120)
        data[:4] = b"\x7fELF"
        data[4:6] = bytes([2, 1])
        struct.pack_into("<H", data, 18, 183)
        struct.pack_into("<Q", data, 32, 64)
        struct.pack_into("<HH", data, 54, 56, 1)
        struct.pack_into("<I", data, 64, 1)
        struct.pack_into("<QQ", data, 72, 0, virtual_address)
        struct.pack_into("<Q", data, 112, alignment)
        return data

    def test_16k_arm64_load_alignment(self):
        segments = apk_validation.validate_load_alignment(self.elf_with_load_segment(), "arm64-v8a")
        self.assertEqual(16384, segments[0]["alignment"])

    def test_4k_load_alignment_rejected_for_arm64(self):
        with self.assertRaisesRegex(ValueError, "not 16384-byte"):
            apk_validation.validate_load_alignment(self.elf_with_load_segment(4096), "arm64-v8a")

    def test_load_offset_address_congruence_required(self):
        with self.assertRaisesRegex(ValueError, "not 16384-byte"):
            apk_validation.validate_load_alignment(self.elf_with_load_segment(16384, 4096), "arm64-v8a")

    def test_arm64_elf_requires_machine_class_and_little_endian(self):
        header = bytearray(20)
        header[:4] = b"\x7fELF"
        header[4:6] = bytes([2, 1])
        header[18:20] = bytes([183, 0])
        self.assertTrue(apk_validation.validate_elf_header(header, "arm64-v8a"))
        self.assertFalse(apk_validation.validate_elf_header(header, "x86_64"))
        header[5] = 2
        self.assertFalse(apk_validation.validate_elf_header(header, "arm64-v8a"))

    def test_non_elf_and_short_bytes_rejected(self):
        self.assertFalse(apk_validation.validate_elf_header(b"not ELF", "arm64-v8a"))
        self.assertFalse(apk_validation.validate_elf_header(b"x" * 20, "arm64-v8a"))

class OptimizedNativeProofTests(unittest.TestCase):
    def synthetic_elf(self, build_id, elf64=True):
        note = struct.pack("<III", 4, len(build_id), 3) + b"GNU\0" + build_id
        program_size = 56 if elf64 else 32
        note_offset = 64 + program_size
        data = bytearray(note_offset + len(note))
        data[:4] = b"\x7fELF"
        data[4:6] = bytes([2 if elf64 else 1, 1])
        struct.pack_into("<Q" if elf64 else "<I", data, 32 if elf64 else 28, 64)
        struct.pack_into("<HH", data, 54 if elf64 else 42, program_size, 1)
        struct.pack_into("<I", data, 64, 4)
        struct.pack_into("<Q" if elf64 else "<I", data, 72 if elf64 else 68, note_offset)
        struct.pack_into("<Q" if elf64 else "<I", data, 96 if elf64 else 80, len(note))
        data[note_offset:] = note
        return bytes(data)

    def test_effective_last_optimization_must_be_o2_or_o3(self):
        good = ["clang++", "-g", "-O2", "-DNDEBUG"]
        self.assertEqual("-O2", native_proof.compiler_flags(good)["effective_optimization"])
        self.assertEqual("-O3", native_proof.compiler_flags(good + ["-O3"])["effective_optimization"])
        with self.assertRaisesRegex(ValueError, "Effective optimization"):
            native_proof.compiler_flags(good + ["-O0"])

    def test_ndebug_cannot_be_undefined_later(self):
        with self.assertRaisesRegex(ValueError, "NDEBUG"):
            native_proof.compiler_flags(["clang++", "-O2", "-g", "-DNDEBUG", "-UNDEBUG"])

    def test_debug_information_must_remain(self):
        with self.assertRaisesRegex(ValueError, "debug information"):
            native_proof.compiler_flags(["clang++", "-O2", "-g", "-DNDEBUG", "-g0"])

    def test_cache_flag_without_build_type_or_abi_is_insufficient(self):
        with self.assertRaisesRegex(ValueError, "RelWithDebInfo"):
            native_proof.require_optimized_cache({"CMAKE_BUILD_TYPE": "Debug", "SEOUL_DS_OPTIMIZED_NATIVE": "ON", "ANDROID_ABI": "arm64-v8a"}, "arm64-v8a")
        with self.assertRaisesRegex(ValueError, "ABI"):
            native_proof.require_optimized_cache({"CMAKE_BUILD_TYPE": "RelWithDebInfo", "SEOUL_DS_OPTIMIZED_NATIVE": "ON", "ANDROID_ABI": "x86_64"}, "arm64-v8a")

    def test_build_id_parser_reads_32_and_64_bit_notes(self):
        expected = bytes(range(20))
        for elf64 in (False, True):
            self.assertEqual(expected.hex(), native_proof.read_gnu_build_id(io.BytesIO(self.synthetic_elf(expected, elf64))))

    def test_missing_and_truncated_build_ids_fail(self):
        data = bytearray(self.synthetic_elf(bytes(range(20))))
        struct.pack_into("<I", data, 64, 1)
        with self.assertRaisesRegex(ValueError, "GNU build ID"):
            native_proof.read_gnu_build_id(io.BytesIO(data))
        with self.assertRaisesRegex(ValueError, "Truncated"):
            native_proof.read_gnu_build_id(io.BytesIO(self.synthetic_elf(bytes(range(20)))[:-1]))

    def test_auto_selection_never_guesses_between_two_graphs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("first", "second"):
                graph = root / "app/.cxx/Debug" / name / "arm64-v8a"
                graph.mkdir(parents=True)
                (graph / "CMakeCache.txt").write_text("CMAKE_BUILD_TYPE:STRING=RelWithDebInfo\nSEOUL_DS_OPTIMIZED_NATIVE:BOOL=ON\nANDROID_ABI:STRING=arm64-v8a\n")
                (graph / "compile_commands.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "found 2"):
                native_proof.select_graph(root, "arm64-v8a")

    def run_synthetic_proof(self, mismatched_apk=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = root / "graph"
            objects = root / "objects"
            graph.mkdir()
            objects.mkdir()
            cache = {"CMAKE_BUILD_TYPE": "RelWithDebInfo", "SEOUL_DS_OPTIMIZED_NATIVE": "ON", "ANDROID_ABI": "arm64-v8a", "CMAKE_MAKE_PROGRAM": "/synthetic/ninja", "CMAKE_NM": "/synthetic/nm", "CMAKE_LIBRARY_OUTPUT_DIRECTORY": str(objects)}
            (graph / "CMakeCache.txt").write_text("".join(f"{k}:STRING={v}\n" for k,v in cache.items()))
            (graph / "compile_commands.json").write_text(json.dumps([{"file": name, "arguments": ["clang++", "-O2", "-g", "-DNDEBUG", "-c", name]} for name in ("NDS.cpp", "MelonDSAndroidJNI.cpp")]))
            apk = root / "synthetic.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                for index, name in enumerate(native_proof.LIBRARIES):
                    expected = bytes([index + 1]) * 20
                    (objects / name).write_bytes(self.synthetic_elf(expected))
                    actual = b"x" * 20 if mismatched_apk and index == 0 else expected
                    archive.writestr(f"lib/arm64-v8a/{name}", self.synthetic_elf(actual))
            def tools(command):
                if "-n" in command:
                    return "ninja: no work to do.\n"
                if "-t" in command:
                    return "object.o: #deps 1\n /synthetic/safe.h\n"
                return "00000000 T safe_symbol\n"
            output = root / "report.json"
            with patch("sys.argv", ["validate_optimized_native.py", "--apk", str(apk), "--native-dir", str(graph), "--json", str(output)]), patch.object(native_proof, "run_checked", side_effect=tools), redirect_stdout(io.StringIO()):
                result = native_proof.main()
            return result, json.loads(output.read_text())

    def test_matching_apk_build_ids_bind_the_graph(self):
        code, report = self.run_synthetic_proof()
        self.assertEqual(0, code)
        self.assertEqual("PASS", report["status"])
        self.assertTrue(all(v["build_ids_match"] for v in report["libraries"].values()))

    def test_stale_apk_cannot_pass_by_optimized_flags_alone(self):
        code, report = self.run_synthetic_proof(mismatched_apk=True)
        self.assertEqual(1, code)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("build IDs differ", report["error"])

class DependencyNoticeTests(unittest.TestCase):
    def test_extracts_nested_aar_license_without_class_bytes(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("META-INF/LICENSE.txt", "Synthetic test license")
            z.writestr("Example.class", b"compiled fixture")
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w") as z:
            z.writestr("classes.jar", inner.getvalue())
        result = notices.archive_notices(outer.getvalue(), "synthetic.aar")
        self.assertEqual(1, len(result))
        self.assertEqual("Synthetic test license", result[0]["text"])
        self.assertEqual("synthetic.aar!/classes.jar!/META-INF/LICENSE.txt", result[0]["source"])

    def test_inherits_parent_pom_license(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            for module, body in (("parent", '<licenses><license><name>Test License</name><url>https://example.invalid/license</url></license></licenses>'), ("child", '<parent><groupId>example</groupId><artifactId>parent</artifactId><version>1</version></parent>')):
                folder = cache / "example" / module / "1" / "hash"
                folder.mkdir(parents=True)
                (folder / f"{module}.pom").write_text('<project xmlns="http://maven.apache.org/POM/4.0.0">' + body + '</project>')
            result = notices.pom_metadata(cache, "example", "child", "1")
            self.assertEqual("Test License", result["licenses"][0]["name"])
            self.assertEqual("example:parent:1", result["license_source"])

    def test_missing_pom_is_audit_error_not_license_guess(self):
        with tempfile.TemporaryDirectory() as directory:
            result = notices.pom_metadata(Path(directory), "missing", "library", "1")
            self.assertIn("error", result)
            self.assertEqual([], result["licenses"])

class PackagingTests(unittest.TestCase):
    def make_repository(self, root):
        (root / "docs").mkdir(parents=True)
        (root / "source.txt").write_text("Synthetic source fixture\n")
        (root / "docs/upstream-lock.json").write_text(json.dumps({"upstream": {"commit": "synthetic"}, "submodules": {}}))
        for args in (("init", "-q"), ("config", "user.name", "Harness fixture"), ("config", "user.email", "fixture@example.invalid"), ("add", "."), ("commit", "-qm", "Synthetic source fixture")):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    def test_clean_source_archive_is_deterministic_and_has_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            self.make_repository(root)
            first, second = Path(directory) / "first.tar.gz", Path(directory) / "second.tar.gz"
            with patch.object(packaging, "ROOT", root):
                for target in (first, second):
                    with patch("sys.argv", ["package_source.py", "--output", str(target)]), redirect_stdout(io.StringIO()):
                        self.assertEqual(0, packaging.main())
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first) as archive:
                manifest_file = next(n for n in archive.getnames() if n.endswith("/SOURCE_MANIFEST.json"))
                manifest = json.loads(archive.extractfile(manifest_file).read())
                self.assertTrue(any(item["path"] == "source.txt" for item in manifest["files"]))
                self.assertFalse(any(".git/" in name for name in archive.getnames()))

    def test_dirty_source_refuses_release_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            self.make_repository(root)
            (root / "source.txt").write_text("Uncommitted change")
            with patch.object(packaging, "ROOT", root), patch("sys.argv", ["package_source.py", "--output", str(Path(directory) / "out.tar.gz")]):
                with self.assertRaisesRegex(RuntimeError, "dirty/untracked"):
                    packaging.main()

    def test_rejects_absolute_parent_and_git_paths(self):
        for name in ("/etc/passwd", "../private", "src/../../private", ".git/config", ""):
            self.assertFalse(packaging.safe_relative(name), name)

    def test_allows_normal_source_path(self):
        self.assertTrue(packaging.safe_relative("melonDS-android-lib/src/android/oboe/LICENSE"))

class StatusTests(unittest.TestCase):
    def test_command_timeout_is_failure_and_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stdout(io.StringIO()):
                result = harness.run_command("synthetic-timeout", [sys.executable, "-c", "import time; time.sleep(10)"], Path(directory), dict(os.environ), 1)
            self.assertEqual("FAIL", result["status"])
            self.assertTrue(result["timed_out"])
            self.assertIsNone(result["exit_code"])

    def test_pending_scope_is_not_pass(self):
        self.assertEqual("INCOMPLETE", harness.overall_status([{"status": "PASS"}, {"status": "PENDING"}]))

    def test_interrupted_partial_report_cannot_claim_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            report = {"mode": "android", "git_commit": "synthetic", "started_at": "synthetic", "checks": [{"name": "self-tests", "status": "PASS"}, {"name": "android-build", "status": "PENDING"}]}
            harness.write_report(report, Path(directory))
            saved = json.loads((Path(directory) / "report.json").read_text())
            self.assertEqual("RUNNING", saved["status"])
            self.assertNotIn("finished_at", saved)
            self.assertEqual("PENDING", saved["checks"][1]["status"])

    def test_completed_report_has_explicit_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            report = {"mode": "static", "git_commit": "synthetic", "started_at": "synthetic", "checks": [{"name": "self-tests", "status": "PASS"}]}
            harness.write_report(report, Path(directory), completed=True)
            self.assertEqual("PASS", report["status"])
            self.assertIn("finished_at", report)

    def test_failure_wins_over_block(self):
        self.assertEqual("FAIL", harness.overall_status([{"status": "PASS"}, {"status": "BLOCKED"}, {"status": "FAIL"}]))

    def test_block_is_not_pass(self):
        self.assertEqual("BLOCKED", harness.overall_status([{"status": "PASS"}, {"status": "BLOCKED"}]))

    def test_not_run_does_not_fake_runtime_pass(self):
        checks = [{"status": "PASS"}, {"status": "NOT RUN"}]
        self.assertEqual("PASS", harness.overall_status(checks))
        self.assertEqual("NOT RUN", checks[1]["status"])

    def test_missing_consent_blocks_android(self):
        issues = harness.android_preflight({"PATH": ""})
        self.assertTrue(any("ANDROID_SDK_LICENSE_ACCEPTED" in issue for issue in issues))
        self.assertTrue(any("ANDROID_HOME" in issue for issue in issues))
        self.assertTrue(any("Java 21" in issue for issue in issues))

    def test_wrong_consent_value_is_not_acceptance(self):
        issues = harness.android_preflight({"PATH": "", "ANDROID_SDK_LICENSE_ACCEPTED": "false"})
        self.assertTrue(any("ANDROID_SDK_LICENSE_ACCEPTED" in issue for issue in issues))

if __name__ == "__main__":
    unittest.main()
