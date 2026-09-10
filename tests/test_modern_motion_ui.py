from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from modern_directory_ui import install_modern_directory_ui
from modern_motion_ui import PAGE_FADE_MS, TOAST_HOLD_MS, install_modern_motion_ui
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui
from workspace_resize_ui import install_workspace_resize_ui


class ModernMotionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        self.window.service.create_demo_data()
        for install in (
            install_backup_features,
            install_csv_features,
            install_assignment_history_features,
            install_temporal_snapshot_features,
            install_service_page_scroll,
            install_workflow_ui,
            install_composition_ui,
            install_workspace_resize_ui,
            install_modern_directory_ui,
            install_modern_motion_ui,
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        animation = getattr(self.window, "modern_motion_page_animation", None)
        if animation is not None:
            animation.stop()
        timer = getattr(self.window, "modern_motion_toast_timer", None)
        if timer is not None:
            timer.stop()
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_install_creates_reusable_motion_layer(self):
        self.assertTrue(self.window._modern_motion_ui_installed)
        self.assertEqual(self.window.modern_motion_toast.objectName(), "modernToast")
        self.assertEqual(self.window.modern_motion_toast_timer.interval(), TOAST_HOLD_MS)
        toast = self.window.modern_motion_toast
        install_modern_motion_ui(self.window)
        self.assertIs(self.window.modern_motion_toast, toast)

    def test_page_change_starts_short_fade(self):
        current = self.window.pages.currentIndex()
        target = 2 if current != 2 else 0
        self.window.pages.setCurrentIndex(target)
        animation = self.window.modern_motion_page_animation
        self.assertIsNotNone(animation)
        self.assertEqual(animation.duration(), PAGE_FADE_MS)
        self.assertIsNotNone(self.window.pages.currentWidget().graphicsEffect())

    def test_toast_can_be_shown_without_blocking(self):
        self.window.show_modern_toast("Готово")
        self.app.processEvents()
        toast = self.window.modern_motion_toast
        self.assertTrue(toast.isVisible())
        self.assertTrue(self.window.modern_motion_toast_timer.isActive())
        text = next(
            label.text()
            for label in toast.findChildren(QLabel)
            if label.objectName() == "modernToastText"
        )
        self.assertEqual(text, "Готово")


if __name__ == "__main__":
    unittest.main()
