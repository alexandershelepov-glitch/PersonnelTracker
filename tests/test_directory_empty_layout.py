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
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui
from workspace_resize_ui import install_workspace_resize_ui


class EmptyDirectoryLayoutTests(unittest.TestCase):
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
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_empty_directory_keeps_remaining_height_in_content_area(self):
        table = self.window.composition_directory_table
        empty = self.window.composition_empty_state
        layout = self.window.composition_directory.layout()

        self.assertEqual(table.rowCount(), 0)
        self.assertFalse(table.isVisible())
        self.assertTrue(empty.isVisible())
        self.assertEqual(layout.stretch(layout.indexOf(table)), 1)
        self.assertEqual(layout.stretch(layout.indexOf(empty)), 1)


if __name__ == "__main__":
    unittest.main()
