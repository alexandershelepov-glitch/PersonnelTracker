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
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui
from workspace_resize_ui import install_workspace_resize_ui


class ModernDirectoryUiTests(unittest.TestCase):
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
        ):
            install(self.window)
        self.window.nav_group.button(0).click()
        self.window.composition_tabs.setCurrentIndex(0)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_reference_screen_has_modern_toolbar_and_actions(self):
        self.assertIsNotNone(self.window.modern_directory_toolbar)
        self.assertEqual(self.window.modern_directory_toolbar.objectName(), "directoryToolbar")
        self.assertIsNotNone(self.window.modern_directory_actions)
        self.assertEqual(self.window.modern_directory_actions.objectName(), "directoryActions")
        self.assertEqual(self.window.composition_search.objectName(), "directorySearch")
        self.assertEqual(self.window.composition_reset_filters.text(), "Сбросить")

    def test_directory_uses_short_helper_and_lightweight_table(self):
        helper = next(
            label
            for label in self.window.composition_directory.findChildren(QLabel)
            if label.objectName() == "directoryIntro"
        )
        self.assertEqual(
            helper.text(),
            "Поиск, фильтры и быстрый доступ к карточкам работников.",
        )
        self.assertFalse(helper.wordWrap())
        self.assertFalse(self.window.composition_directory_table.showGrid())
        self.assertIn("Добавьте работников", self.window.composition_empty_state.text())

    def test_install_is_idempotent(self):
        toolbar = self.window.modern_directory_toolbar
        install_modern_directory_ui(self.window)
        self.assertIs(self.window.modern_directory_toolbar, toolbar)
        matches = [
            child
            for child in self.window.composition_directory.findChildren(type(toolbar))
            if child.objectName() == "directoryToolbar"
        ]
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
