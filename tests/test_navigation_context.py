from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from csv_data import install_csv_features
from navigation_context import install_context_navigation
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class ContextNavigationTests(unittest.TestCase):
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
            install_context_navigation,
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()
        self.today_index = self.window.pages.indexOf(self.window.today_page)

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_contextual_root_keeps_back_history(self):
        # Today -> detailed state -> Planning is a contextual chain even though
        # Planning is also a sidebar root.
        self.window._select_page(3)
        self.window._select_page(2)
        self.assertEqual(self.window.pages.currentIndex(), 2)
        self.assertTrue(self.window._context_back_buttons[2].isVisible())

        self.window.navigate_back()
        self.assertEqual(self.window.pages.currentIndex(), 3)
        self.assertTrue(self.window._context_back_buttons[3].isVisible())

        self.window.navigate_back()
        self.assertEqual(self.window.pages.currentIndex(), self.today_index)
        self.assertFalse(any(button.isVisible() for button in self.window._context_back_buttons.values()))

    def test_sidebar_root_clears_back_history(self):
        self.window._select_page(3)
        self.assertTrue(self.window._navigation_stack)

        planning_button = self.window.nav_group.button(2)
        planning_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.pages.currentIndex(), 2)
        self.assertFalse(self.window._navigation_stack)
        self.assertFalse(self.window._context_back_buttons[2].isVisible())


if __name__ == "__main__":
    unittest.main()
