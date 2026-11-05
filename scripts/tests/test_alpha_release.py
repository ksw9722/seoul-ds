"""Fail-closed alpha publication policy and verification prerequisites."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
release = load('prepare_alpha_release')
audit = load('audit_source')

class AlphaReleaseTests(unittest.TestCase):
    def setUp(self):
        self.report = {'status': 'PASS', 'mode': 'android', 'git_commit': 'abc', 'git_worktree': '', 'abi': 'arm64-v8a', 'optimized_native_requested': True, 'checks': [{'name': name, 'status': 'PASS'} for name in release.REQUIRED_CHECKS] + [{'name': 's24-and-game-runtime', 'status': 'NOT RUN'}]}

    def test_complete_verified_report_passes(self):
        release.validate_report(self.report, 'abc')

    def test_wrong_commit_fails(self):
        with self.assertRaises(ValueError): release.validate_report(self.report, 'other')

    def test_each_missing_check_fails(self):
        for name in release.REQUIRED_CHECKS:
            report = copy.deepcopy(self.report)
            report['checks'] = [c for c in report['checks'] if c['name'] != name]
            with self.assertRaises(ValueError, msg=name): release.validate_report(report, 'abc')

    def test_failed_or_blocked_check_fails(self):
        for status in ('FAIL', 'BLOCKED', 'PENDING', 'NOT RUN'):
            report = copy.deepcopy(self.report)
            report['checks'][0]['status'] = status
            with self.assertRaises(ValueError): release.validate_report(report, 'abc')

    def test_unverified_inputs_fail(self):
        for key, value in [('status', 'FAIL'), ('mode', 'static'), ('git_worktree', ' M source'), ('abi', 'x86_64'), ('optimized_native_requested', False)]:
            report = {**self.report, key: value}
            with self.assertRaises(ValueError, msg=key): release.validate_report(report, 'abc')

    def test_invented_runtime_pass_fails(self):
        self.report['checks'][-1]['status'] = 'PASS'
        with self.assertRaises(ValueError): release.validate_report(self.report, 'abc')

    def test_write_capable_workflow_exactly_matches_reviewed_policy(self):
        data = (ROOT / '.github/workflows/alpha-release.yml').read_bytes()
        self.assertEqual(audit.APPROVED_ALPHA_WORKFLOW_SHA256, hashlib.sha256(data).hexdigest())
        self.assertNotEqual(audit.APPROVED_ALPHA_WORKFLOW_SHA256, hashlib.sha256(data.replace(b'--prerelease', b'--latest')).hexdigest())
        text = data.decode()
        before, publish = text.split('\n  publish:\n')
        self.assertNotIn('contents: write', before)
        self.assertNotIn('actions/checkout', publish)
        self.assertNotIn('pull_request:', text)
        self.assertIn("needs: build", publish)
        self.assertIn("needs.build.result == 'success'", publish)
        self.assertIn('sha256sum --check SHA256SUMS.txt', publish)
        self.assertIn('--draft=false --prerelease --latest=false', publish)
        self.assertIn("inputs.accept_android_sdk_terms == true", before)
        self.assertIn("vars.ANDROID_SDK_LICENSE_ACCEPTED == 'true'", before)

if __name__ == '__main__': unittest.main()
