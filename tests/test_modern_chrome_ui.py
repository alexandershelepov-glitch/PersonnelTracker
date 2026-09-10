from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from modern_chrome_ui import install_modern_chrome_ui
from modern_directory_ui import install_modern_directory_ui
from modern_elevation_ui import install_modern_elevation_ui
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui
from workspace_resize_ui import install_workspace_resize_ui


class ModernChromeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
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
            install_modern_elevation_ui,
            install_modern_chrome_ui,
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_sidebar_uses_icons_and_soft_active_accent(self):
        by_text = {button.text(): button for button in self.window.modern_sidebar_buttons}
        self.assertEqual(set(by_text), {"Сегодня", "Состав", "Планирование", "Настройки"})
        for button in by_text.values():
            self.assertFalse(button.icon().isNull())
        self.assertIn("border-left: 3px solid", self.window.modern_sidebar.styleSheet())
        self.assertLessEqual(self.window.modern_sidebar.maximumWidth(), 224)

    def test_directory_actions_receive_vector_icons(self):
        self.assertIsNotNone(self.window.modern_search_action)
        self.assertFalse(self.window.modern_search_action.icon().isNull())
        directory = self.window.composition_directory
        buttons = {button.text(): button for button in directory.findChildren(QPushButton)}
        self.assertFalse(buttons["Копировать"].icon().isNull())
        self.assertFalse(buttons["Открыть карточку"].icon().isNull())
        self.assertFalse(buttons["Сбросить"].icon().isNull())

    def test_install_is_idempotent(self):
        sidebar = self.window.modern_sidebar
        action = self.window.modern_search_action
        install_modern_chrome_ui(self.window)
        self.assertIs(self.window.modern_sidebar, sidebar)
        self.assertIs(self.window.modern_search_action, action)


if __name__ == "__main__":
    unittest.main()
