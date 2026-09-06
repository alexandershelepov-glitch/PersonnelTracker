from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from config import EVENT_TYPES
from event_colors import EVENT_HUES, event_background
from theme import ThemeManager


class EventColorTests(unittest.TestCase):
    def test_every_event_type_has_unique_stable_hue(self):
        self.assertEqual(set(EVENT_HUES), set(EVENT_TYPES))
        self.assertEqual(len(set(EVENT_HUES.values())), len(EVENT_HUES))

    def test_event_backgrounds_are_distinct_and_theme_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.IniFormat)
            settings.setValue(ThemeManager.SETTINGS_KEY, ThemeManager.LIGHT)
            light = ThemeManager(settings)
            vacation_light = event_background("Отпуск", light)
            sick_light = event_background("Больничный", light)
            self.assertNotEqual(vacation_light.name(), sick_light.name())

            settings.setValue(ThemeManager.SETTINGS_KEY, ThemeManager.DARK)
            dark = ThemeManager(settings)
            vacation_dark = event_background("Отпуск", dark)
            self.assertNotEqual(vacation_light.name(), vacation_dark.name())


if __name__ == "__main__":
    unittest.main()
