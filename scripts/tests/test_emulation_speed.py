"""Speed-control wiring checks; native behavioral tests run in native_host_tests.py."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ANDROID = "{http://schemas.android.com/apk/res/android}"


def source(path):
    return (ROOT / path).read_text()


class EmulationSpeedWiringTests(unittest.TestCase):
    def test_jni_and_kotlin_signatures_match(self):
        kotlin = source("app/src/main/java/me/magnum/melonds/MelonEmulator.kt")
        native = source("app/src/main/cpp/MelonDSAndroidJNI.cpp")
        for method in ("cycleEmulationSpeed", "getEmulationSpeed"):
            self.assertIn(f"external fun {method}(): Int", kotlin)
            self.assertIn(f"JNIEXPORT jint JNICALL\nJava_me_magnum_melonds_MelonEmulator_{method}", native)
        self.assertNotIn("setFastForwardEnabled", kotlin + native)

    def test_speed_requests_do_not_touch_hint_session_from_ui_thread(self):
        native = source("app/src/main/cpp/MelonDSAndroidJNI.cpp")
        jni, loop = native.split("void* emulate(void*)\n", 1)
        self.assertNotIn("performanceHintSession", jni)
        self.assertIn("const auto timing = emulationSpeed.timing();", loop)
        self.assertIn("timing.targetFps", loop)
        self.assertIn("updateTargetWorkDuration(timing.targetWorkDurationNs)", loop)

    def test_obsolete_unlimited_preference_cannot_override_live_speed(self):
        preferences = ET.parse(ROOT / "app/src/main/res/xml/pref_general.xml").getroot()
        keys = {item.attrib.get(ANDROID + "key") for item in preferences}
        self.assertNotIn("fast_forward_speed_multiplier", keys)
        self.assertIn("emulation_speed_info", keys)
        for path in (
            "app/src/main/java/me/magnum/melonds/domain/model/EmulatorConfiguration.kt",
            "app/src/main/java/me/magnum/melonds/impl/SharedPreferencesSettingsRepository.kt",
            "app/src/main/cpp/MelonDSAndroidConfiguration.cpp",
            "app/src/main/cpp/MelonDSAndroidJNI.cpp",
        ):
            self.assertNotIn("fastForwardSpeedMultiplier", source(path), path)

    def test_native_speed_survives_settings_and_ui_recreation(self):
        activity = source("app/src/main/java/me/magnum/melonds/ui/emulator/EmulatorActivity.kt")
        self.assertNotIn("var fastForwardEnabled", activity)
        self.assertIn("val multiplier = MelonEmulator.cycleEmulationSpeed()", activity)
        self.assertRegex(activity, r"emulatorState\.collectLatest\s*\{\s*updateEmulationSpeedFeedback\(\)")
        self.assertIn("val multiplier = MelonEmulator.getEmulationSpeed()", activity)
        for target in ("binding.viewLayoutControls", "presentation?.layoutView?"):
            self.assertIn(f"{target}.setLayoutComponentToggleState(LayoutComponent.BUTTON_FAST_FORWARD_TOGGLE, multiplier > 1)", activity)

    def test_short_toast_remains_without_custom_top_placement(self):
        activity = source("app/src/main/java/me/magnum/melonds/ui/emulator/EmulatorActivity.kt")
        self.assertIn("speedToast?.cancel()", activity)
        self.assertIn("Toast.makeText(this@EmulatorActivity, getString(R.string.emulation_speed_status, multiplier), Toast.LENGTH_SHORT)", activity)
        self.assertIn("speedToast?.show()", activity)
        self.assertNotIn("setGravity", activity)

    def test_holding_controller_key_does_not_cycle_repeatedly(self):
        processor = source("app/src/main/java/me/magnum/melonds/ui/emulator/input/InputProcessor.kt")
        self.assertRegex(processor, r"if \(input == Input.FAST_FORWARD && keyEvent.repeatCount > 0\) return true")

    def test_no_speed_badge_on_main_or_external_display(self):
        for path in (
            "app/src/main/res/layout/activity_emulator.xml",
            "app/src/main/res/xml/scene_activity_emulator.xml",
            "app/src/main/java/me/magnum/melonds/ui/emulator/EmulatorActivity.kt",
            "app/src/main/java/me/magnum/melonds/ui/emulator/render/ExternalPresentation.kt",
        ):
            text = source(path)
            for obsolete in ("EmulationSpeedIndicator", "textEmulationSpeed", "speedIndicator", "showEmulationSpeed"):
                self.assertNotIn(obsolete, text, path)
        self.assertFalse((ROOT / "app/src/main/java/me/magnum/melonds/ui/emulator/speed/EmulationSpeedIndicator.kt").exists())

    def test_unrelated_fps_and_two_player_indicators_remain(self):
        for path in ("layout/activity_emulator.xml", "xml/scene_activity_emulator.xml"):
            layout = ET.parse(ROOT / "app/src/main/res" / path).getroot()
            ids = {item.attrib.get(ANDROID + "id") for item in layout.iter()}
            self.assertIn("@+id/textFps", ids)
            self.assertIn("@+id/text_two_player", ids)

    def test_english_and_korean_feedback_have_matching_format(self):
        for locale, suffix in (("values", "×"), ("values-ko", "배")):
            strings = ET.parse(ROOT / f"app/src/main/res/{locale}/strings_emulation_speed.xml").getroot()
            values = {item.attrib["name"]: item.text for item in strings}
            self.assertIn("%1$d", values["emulation_speed_status"])
            expected_cycle = " → ".join(f"{speed}{suffix}" for speed in (1, 5, 10, 1))
            self.assertIn(expected_cycle, values["emulation_speed_cycle_summary"])
            self.assertIn(f"1{suffix} / 5{suffix} / 10{suffix}", values["emulation_speed_cycle_input"])

    def test_new_session_and_stop_reset_native_speed(self):
        native = source("app/src/main/cpp/MelonDSAndroidJNI.cpp")
        for method in ("startEmulation", "stopEmulation"):
            body = native.split(f"Java_me_magnum_melonds_MelonEmulator_{method}", 1)[1].split("JNIEXPORT", 1)[0]
            self.assertIn("emulationSpeed.reset();", body)

    def test_two_player_activation_and_cycle_are_serialized(self):
        native = source("app/src/main/cpp/MelonDSAndroidJNI.cpp")
        cycle = native.split("Java_me_magnum_melonds_MelonEmulator_cycleEmulationSpeed", 1)[1].split("JNIEXPORT", 1)[0]
        self.assertIn("emulationSpeedMutex", cycle)
        self.assertIn("MelonDSAndroid::isTwoPlayerActive()", cycle)
        self.assertIn("EmulationSpeedController::NORMAL_SPEED", cycle)
        start = native.split("Java_me_magnum_melonds_MelonEmulator_startSecondPlayerInternal", 1)[1].split("JNIEXPORT", 1)[0]
        self.assertRegex(start, r"if \(result == 0\) \{\s*std::lock_guard<std::mutex> speedLock\(emulationSpeedMutex\);\s*emulationSpeed.reset\(\);")


if __name__ == "__main__":
    unittest.main()
