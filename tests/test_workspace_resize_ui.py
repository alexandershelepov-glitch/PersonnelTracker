from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from composition_ui import install_composition_ui
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
        install_composition_ui(self.window)
        install_planning_ui(self.window)
        summary_root = self.window.summary_table.parentWidget().layout()
        self.summary_root = summary_root
        self.old_summary_bottom_layout = next(
            summary_root.itemAt(index).layout()
            for index in range(summary_root.count())
            if summary_root.itemAt(index).layout() is not None
            and summary_root.itemAt(index).layout().indexOf(self.window.summary_tree) >= 0
        )
        install_workspace_resize_ui(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_directory_columns_are_movable_persistent_and_resettable(self):
        table = self.window.composition_directory_table
        header = self.window.directory_header
        self.assertTrue(header.sectionsMovable())
        self.assertTrue(table.isColumnHidden(6))
        for column in range(6):
            self.assertEqual(header.sectionResizeMode(column), QHeaderView.Interactive)

        header.moveSection(0, 2)
        table.setColumnWidth(1, 260)
        self.app.processEvents()
        self.assertEqual(header.visualIndex(0), 2)
        self.assertIsNotNone(self.window.settings.value("workspace/directory_header_state"))

        self.window.reset_directory_columns_action.trigger()
        self.app.processEvents()
        self.assertEqual(header.visualIndex(0), 0)
        self.assertEqual(table.columnWidth(0), 220)
        self.assertIsNone(self.window.settings.value("workspace/directory_header_state"))

    def _open_new_window(self):
        """A second app window sharing the same QSettings file."""
        other = MainWindow(Path(self.tmp.name) / "personnel_other.db")
        install_composition_ui(other)
        install_planning_ui(other)
        install_workspace_resize_ui(other)
        other.show()
        self.app.processEvents()
        return other

    def test_directory_layout_survives_restart_and_reset_clears_it(self):
        # 1. Change the directory order and width in the first window.
        header = self.window.directory_header
        header.moveSection(0, 2)
        self.window.composition_directory_table.setColumnWidth(1, 260)
        self.app.processEvents()
        self.assertEqual(header.visualIndex(0), 2)
        self.assertIsNotNone(self.window.settings.value("workspace/directory_header_state"))

        # 2. A new window with the same settings restores the user layout.
        second = self._open_new_window()
        try:
            self.assertEqual(second.directory_header.visualIndex(0), 2)
            self.assertEqual(second.composition_directory_table.columnWidth(1), 260)
        finally:
            second.close()
            second.deleteLater()
            self.app.processEvents()

        # 3. Reset in another window restores the factory layout and drops the key.
        resetter = self._open_new_window()
        try:
            resetter.reset_directory_columns_action.trigger()
            self.app.processEvents()
            self.assertEqual(resetter.directory_header.visualIndex(0), 0)
            self.assertEqual(resetter.composition_directory_table.columnWidth(0), 220)
            self.assertIsNone(resetter.settings.value("workspace/directory_header_state"))
        finally:
            resetter.close()
            resetter.deleteLater()
            self.app.processEvents()

        # 4. Yet another window must open factory-default, not the old user layout.
        third = self._open_new_window()
        try:
            self.assertEqual(third.directory_header.visualIndex(0), 0)
            self.assertEqual(third.composition_directory_table.columnWidth(0), 220)
            self.assertTrue(third.composition_directory_table.isColumnHidden(6))
        finally:
            third.close()
            third.deleteLater()
            self.app.processEvents()

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

    def test_summary_layout_is_replaced_once_with_nested_splitters(self):
        root = self.summary_root
        vertical = self.window.summary_vertical_splitter
        horizontal = self.window.summary_horizontal_splitter

        self.assertEqual(root.indexOf(self.old_summary_bottom_layout), -1)
        self.assertGreaterEqual(root.indexOf(vertical), 0)
        self.assertGreaterEqual(vertical.indexOf(horizontal), 0)
        self.assertGreaterEqual(horizontal.indexOf(self.window.summary_tree), 0)
        self.assertGreaterEqual(horizontal.indexOf(self.window.summary_people), 0)

        top_panel = vertical.widget(0)
        self.assertGreaterEqual(top_panel.layout().indexOf(self.window.summary_table), 0)
        self.assertGreaterEqual(top_panel.layout().indexOf(self.window.diagnostic_label), 0)

        root_count = root.count()
        install_workspace_resize_ui(self.window)
        self.assertIs(self.window.summary_vertical_splitter, vertical)
        self.assertIs(self.window.summary_horizontal_splitter, horizontal)
        self.assertEqual(root.count(), root_count)


if __name__ == "__main__":
    unittest.main()
