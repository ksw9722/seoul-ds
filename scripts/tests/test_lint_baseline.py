"""Keep the reviewed partial-localization exception precise, never a runtime-error waiver."""
import hashlib
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


class LintLocalizationDebtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.issues = ET.parse(ROOT / "app/lint-baseline.xml").getroot().findall("issue")

    def test_exact_reviewed_missing_translation_count_only(self):
        self.assertEqual(372, len(self.issues))
        self.assertEqual({"MissingTranslation"}, {i.get("id") for i in self.issues})

    def test_no_absolute_wildcard_or_runtime_source_locations(self):
        locations = [l.get("file") for i in self.issues for l in i.findall("location")]
        self.assertEqual(372, len(locations))
        self.assertEqual({"src/main/res/values/strings.xml"}, set(locations))

    def test_replacing_entries_requires_an_explicit_review(self):
        records = sorted((i.get("id"), i.get("message"), tuple(l.get("file") for l in i.findall("location"))) for i in self.issues)
        fingerprint = hashlib.sha256(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual("6ec8b836ba21732489076cae4c211f39c4e892ed88a4d11ef96e90e3bbd8eb11", fingerprint)

    def test_korean_and_upstream_debt_are_not_conflated(self):
        only_korean = mixed = only_existing = 0
        for issue in self.issues:
            locales = set(re.findall(r'"([a-z]+)" \(', issue.get("message")))
            if locales == {"ko"}:
                only_korean += 1
            elif "ko" in locales:
                mixed += 1
            else:
                only_existing += 1
        self.assertEqual((195, 170, 7), (only_korean, mixed, only_existing))

    def test_spanish_rewind_time_has_both_typed_placeholders(self):
        strings = ET.parse(ROOT / "app/src/main/res/values-b+es/strings.xml").getroot()
        text = next(e.text for e in strings if e.get("name") == "rewind_time_minutes_seconds")
        self.assertEqual([("1", "d"), ("2", "s")], re.findall(r"%([0-9]+)\$([a-z])", text))

    def test_russian_pending_counts_define_required_categories(self):
        strings = ET.parse(ROOT / "app/src/main/res/values-b+ru/strings.xml").getroot()
        for key in ("retroachievements_pending_achievement_unlocks", "retroachievements_pending_leaderboard_entries"):
            with self.subTest(key=key):
                plural = next(e for e in strings if e.get("name") == key)
                self.assertEqual({"one", "few", "many", "other"}, {i.get("quantity") for i in plural})
                self.assertTrue(all("%d" in i.text for i in plural))


if __name__ == "__main__":
    unittest.main()
