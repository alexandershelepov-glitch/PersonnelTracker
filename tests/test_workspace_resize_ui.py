from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from planning_ui import install_planning_ui
from ui import MainWindow
from workspace_resize_ui import install_workspace_resize_ui


class WorkspaceResizeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        install_planning_ui(self.window)
        install_workspace_resize_ui(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_planning_identity_columns_are_interactive_and_persist(self):
        header = self.window.planning_people_table.horizontalHeader()
        for column in range(3):
            self.assertEqual(header.sectionResizeMode(column), QHeaderView.Interactive)

        self.window.planning_people_table.setColumnWidth(0, 245)
        self.app.processEvents()
        self.assertIsNotNone(self.window.settings.value("planning/people_header_state"))

    def test_summary_workspaces_use_saved_splitters(self):
        vertical = self.window.summary_vertical_splitter
        horizontal = self.window.summary_horizontal_splitter
        self.assertEqual(vertical.orientation(), Qt.Vertical)
        self.assertEqual(horizontal.orientation(), Qt.Horizontal)
        self.assertFalse(vertical.childrenCollapsible())
        self.assertFalse(horizontal.childrenCollapsible())

        vertical.moveSplitter(260, 1)
        horizontal.moveSplitter(420, 1)
        self.app.processEvents()
        self.assertIsNotNone(self.window.settings.value("summary/vertical_splitter_state"))
        self.assertIsNotNone(self.window.settings.value("summary/horizontal_splitter_state"))


if __name__ == "__main__":
    unittest.main()
