from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from modern_chrome_ui import install_modern_chrome_ui
from service_page_scroll import install_service_page_scroll
from sidebar_collapse_ui import install_sidebar_collapse_ui
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class SidebarCollapseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=self.settings)
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
            install_modern_chrome_ui,
            install_sidebar_collapse_ui,
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_collapse_hides_labels_and_expands_back(self):
        self.window.set_sidebar_collapsed(True)
        self.app.processEvents()
        self.assertTrue(self.window.sidebar_collapsed)
        self.assertEqual(self.window.modern_sidebar.minimumWidth(), 62)
        self.assertEqual(self.window.modern_sidebar.maximumWidth(), 62)
        for button in self.window.modern_sidebar_buttons:
            self.assertEqual(button.text(), "")
            self.assertTrue(button.toolTip())
            self.assertFalse(button.icon().isNull())

        self.window.set_sidebar_collapsed(False)
        self.app.processEvents()
        self.assertFalse(self.window.sidebar_collapsed)
        self.assertGreaterEqual(self.window.modern_sidebar.minimumWidth(), 196)
        labels = {button.text() for button in self.window.modern_sidebar_buttons}
        self.assertEqual(labels, {"Сегодня", "Состав", "Планирование", "Настройки"})

    def test_collapsed_state_is_persisted(self):
        self.window.set_sidebar_collapsed(True)
        self.settings.sync()
        value = self.settings.value("ui/sidebar_collapsed")
        self.assertIn(str(value).lower(), {"true", "1"})

    def test_navigation_recolouring_survives_hidden_text(self):
        self.window.set_sidebar_collapsed(True)
        target = self.window.modern_sidebar_buttons[1]
        target.setChecked(True)
        self.app.processEvents()
        self.assertEqual(target.text(), "")
        self.assertFalse(target.icon().isNull())


if __name__ == "__main__":
    unittest.main()
