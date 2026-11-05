"""Flat vendoring must preserve and verify the original source, not fake gitlinks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('audit_source', Path(__file__).resolve().parents[1] / 'audit_source.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class FlatProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'docs').mkdir()
        (self.root / 'vendor').mkdir()
        self.source = self.root / 'vendor/source.c'
        self.source.write_text('original source')
        lock = {'upstream': {'commit': 'upstream'}, 'submodules': {'vendor': 'module-commit'}}
        self.original = {'root_commit': 'original-commit', **lock, 'files': [{'path': 'vendor/source.c', 'sha256': audit.sha256(self.source)}]}
        (self.root / 'docs/upstream-lock.json').write_text(json.dumps(lock))
        self.write_manifest()

    def write_manifest(self):
        path = self.root / 'docs/original-source-manifest.json'
        path.write_text(json.dumps(self.original))
        (self.root / 'docs/publication-snapshot.json').write_text(json.dumps({'layout': 'flat-vendored', 'original_source_commit': 'original-commit', 'original_manifest_sha256': audit.sha256(path)}))

    def test_unchanged_vendored_source_passes(self):
        audit.verify_vendored_provenance(self.root, [self.source])

    def test_modified_vendored_source_fails(self):
        self.source.write_text('changed')
        with self.assertRaisesRegex(AssertionError, 'hash mismatch'):
            audit.verify_vendored_provenance(self.root, [self.source])

    def test_missing_vendored_source_fails(self):
        with self.assertRaisesRegex(AssertionError, 'inventory differs'):
            audit.verify_vendored_provenance(self.root, [])

    def test_extra_vendored_source_fails(self):
        extra = self.root / 'vendor/extra.c'
        extra.write_text('extra')
        with self.assertRaisesRegex(AssertionError, 'inventory differs'):
            audit.verify_vendored_provenance(self.root, [self.source, extra])

    def test_original_manifest_tampering_fails(self):
        (self.root / 'docs/original-source-manifest.json').write_text('{}')
        with self.assertRaisesRegex(AssertionError, 'manifest hash mismatch'):
            audit.verify_vendored_provenance(self.root, [self.source])

    def test_changed_upstream_identity_fails(self):
        self.original['upstream']['commit'] = 'changed'
        self.write_manifest()
        with self.assertRaisesRegex(AssertionError, 'provenance differs'):
            audit.verify_vendored_provenance(self.root, [self.source])

    def test_gitlink_in_flat_checkout_fails(self):
        (self.root / '.git').mkdir()
        with patch.object(audit, 'git', return_value='160000 abc 0\tvendor'):
            with self.assertRaisesRegex(AssertionError, 'gitlinks'):
                audit.verify_vendored_provenance(self.root, [self.source])

if __name__ == '__main__':
    unittest.main()
