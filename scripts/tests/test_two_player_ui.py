"""Static UI/SAF contracts only. These do not validate Android or game execution."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BASE = "app/src/main/java/me/magnum/melonds/"


def read(path):
    return (ROOT / path).read_text()


class TwoPlayerUiContractTests(unittest.TestCase):
    def test_second_player_only_receives_private_copy(self):
        manager = read(BASE + "impl/emulator/AndroidEmulatorManager.kt")
        self.assertIn('TwoPlayerSaveFiles(File(context.filesDir, "two-player"))', manager)
        self.assertIn("openInputStream(uri)", manager)
        self.assertIn("MelonEmulator.startSecondPlayer(romUri, Uri.fromFile(secondary))", manager)
        self.assertNotIn("openOutputStream(importedSave", manager)
        self.assertIn("DocumentsContract.getDocumentId(first) == DocumentsContract.getDocumentId(second)", manager)
        self.assertIn("firstStat.st_dev == secondStat.st_dev && firstStat.st_ino == secondStat.st_ino", manager)

    def test_flush_failure_blocks_backup_and_export(self):
        manager = read(BASE + "impl/emulator/AndroidEmulatorManager.kt")
        start = manager.split("override suspend fun startSecondPlayer", 1)[1].split("override suspend fun selectPlayer", 1)[0]
        self.assertLess(start.index("if (!MelonEmulator.flushSaveFiles())"), start.index("twoPlayerSaves.prepare"))
        export = manager.split("override suspend fun exportTwoPlayerSave", 1)[1].split("private fun sameDocument", 1)[0]
        self.assertLess(export.index("if (!MelonEmulator.flushSaveFiles())"), export.index("openOutputStream"))

    def test_saved_dialog_state_cannot_strand_recreated_activity(self):
        activity = read(BASE + "ui/emulator/EmulatorActivity.kt")
        self.assertIn('outState.putBoolean("two_player_picker_pending", twoPlayerPickerPending)', activity)
        self.assertNotIn('outState.putBoolean("two_player_flow_pending"', activity)
        self.assertIn("viewModel.isTwoPlayerOperationRunning() || viewModel.twoPlayerResult.value != null", activity)
        self.assertIn("viewModel.twoPlayerResult.collect", activity)
        self.assertIn("viewModel.consumeTwoPlayerResult()", activity)
        model = read(BASE + "ui/emulator/EmulatorViewModel.kt")
        self.assertIn("MutableStateFlow<EmulatorUiEvent?>(null)", model)
        self.assertIn("!isActivityResumed || twoPlayerOperationRunning", model)

    def test_state_and_reset_hotkeys_are_guarded(self):
        model = read(BASE + "ui/emulator/EmulatorViewModel.kt")
        for method in ("resetEmulator", "doQuickSave", "doQuickLoad", "onOpenRewind", "rewindToState", "saveStateToSlot", "loadStateFromSlot"):
            self.assertRegex(model, rf"fun {method}\([^)]*\) \{{\s*if \(blockUnsupportedTwoPlayerOperation\(\)\) return")
        self.assertIn("setOf(RomPauseMenuOption.TWO_PLAYER, RomPauseMenuOption.SWITCH_PLAYER, RomPauseMenuOption.EXIT)", model)

    def test_resources_match_and_warn_about_unverified_compatibility(self):
        locales = []
        for locale in ("values", "values-ko"):
            root = ET.parse(ROOT / f"app/src/main/res/{locale}/strings_twoplayer.xml").getroot()
            locales.append({node.attrib["name"]: node.text for node in root})
        self.assertEqual(locales[0].keys(), locales[1].keys())
        self.assertIn("unverified", locales[0]["two_player_warning"])
        self.assertIn("uninstalled", locales[0]["two_player_warning"])
        self.assertIn("%1$d", locales[0]["two_player_current"])
        used = set(re.findall(r"R\.string\.(two_player_\w+)", read(BASE + "ui/emulator/EmulatorActivity.kt") + read(BASE + "ui/emulator/rom/RomPauseMenuOption.kt")))
        self.assertFalse(used - locales[0].keys())

    def test_replacement_needs_explicit_confirmation_and_offers_export(self):
        activity = read(BASE + "ui/emulator/EmulatorActivity.kt")
        self.assertEqual(2, activity.count("confirmTwoPlayerReplacement(saves.hasPlayerTwoSave)"))
        confirmation = activity.split("private fun confirmTwoPlayerReplacement", 1)[1].split("private fun launchTwoPlayerExport", 1)[0]
        self.assertIn(".setPositiveButton(R.string.two_player_export_first) { _, _ -> launchTwoPlayerExport(false) }", confirmation)
        self.assertIn(".setNeutralButton(R.string.two_player_replace_anyway) { _, _ -> onConfirmed() }", confirmation)
        self.assertIn(".setOnCancelListener { finishTwoPlayerFlow() }", confirmation)

    def test_slow_native_achievement_calls_are_off_main(self):
        manager = read(BASE + "impl/emulator/AndroidEmulatorManager.kt")
        self.assertIn("override suspend fun updateCheats(cheats: List<Cheat>) = withContext(stateDispatcher)", manager)
        self.assertIn("override suspend fun setupRetroAchievements(achievementData: GameAchievementData) = withContext(stateDispatcher)", manager)
        self.assertIn("override suspend fun unloadRetroAchievementsData() = withContext(stateDispatcher)", manager)
        model = read(BASE + "ui/emulator/EmulatorViewModel.kt")
        self.assertIn("withContext(Dispatchers.IO) { MelonEmulator.getRichPresenceStatus() }", model)

    def test_native_failure_is_not_dropped(self):
        manager = read(BASE + "impl/emulator/AndroidEmulatorManager.kt")
        self.assertIn("Unknown -> EmulatorEvent.Stop.Reason.InternalError", manager)
        model = read(BASE + "ui/emulator/EmulatorViewModel.kt")
        self.assertIn("EmulatorEvent.Stop.Reason.InternalError,", model)


if __name__ == "__main__":
    unittest.main()
