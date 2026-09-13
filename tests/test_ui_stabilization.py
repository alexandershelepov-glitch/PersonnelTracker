"""Cross-cutting v1.1 UI stabilization regressions.

These tests guard the class of defects found during the stabilization pass:
table geometry must survive refresh/date/theme changes, technical ID columns
must stay hidden, resets must clear their QSettings state, and semantic
calendar columns must never become user-movable.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate, QSettings
from PySide6.QtWidgets import QApplication, QHeaderView

from composition_ui import install_composition_ui
from custom_workspace_ui import install_custom_workspace_ui
from interface_polish import install_interface_polish
from modern_directory_ui import install_modern_directory_ui
from planning_ui import install_planning_ui
from ui import MainWindow
from workflow_ui import install_workflow_ui
from workspace_resize_ui import install_workspace_resize_ui


class UiStabilizationRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        self.window.service.create_demo_data()
        # Mirrors the application install order for the layers under test.
        for install in (
            install_workflow_ui,
            install_composition_ui,
            install_planning_ui,
            install_interface_polish,
            install_workspace_resize_ui,
            install_modern_directory_ui,
            install_custom_workspace_ui,
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_today_width_survives_date_change(self):
        table = self.window.today_page.absent_table
        changed = table.columnWidth(0) + 53
        table.setColumnWidth(0, changed)
        self.app.processEvents()

        self.window.today_page.set_date(QDate(2026, 9, 5))
        self.app.processEvents()
        self.window.today_page.set_date(QDate(2026, 8, 20))
        self.app.processEvents()

        self.assertEqual(table.columnWidth(0), changed)
        self.assertEqual(table.horizontalHeader().sectionResizeMode(0), QHeaderView.Interactive)

    def test_directory_width_survives_refresh_all(self):
        table = self.window.composition_directory_table
        changed = table.columnWidth(0) + 37
        table.setColumnWidth(0, changed)
        self.app.processEvents()

        self.window.refresh_all()
        self.app.processEvents()

        self.assertEqual(table.columnWidth(0), changed)
        self.assertEqual(table.horizontalHeader().sectionResizeMode(0), QHeaderView.Interactive)

    def test_theme_change_keeps_table_geometry(self):
        today_table = self.window.today_page.absent_table
        directory_table = self.window.composition_directory_table
        today_width = today_table.columnWidth(1) + 41
        directory_width = directory_table.columnWidth(0) + 29
        today_table.setColumnWidth(1, today_width)
        directory_table.setColumnWidth(0, directory_width)
        self.app.processEvents()

        self.window.toggle_theme()
        self.app.processEvents()

        self.assertEqual(today_table.columnWidth(1), today_width)
        self.assertEqual(directory_table.columnWidth(0), directory_width)

    def test_hidden_technical_columns_stay_hidden_after_reset_and_theme(self):
        directory = self.window.composition_directory_table
        planning_list = self.window.planning_list_table
        shds = self.window.staff_table

        self.assertTrue(directory.isColumnHidden(6))
        self.assertTrue(planning_list.isColumnHidden(8))
        self.assertTrue(shds.isColumnHidden(0))

        self.window.reset_directory_columns_action.trigger()
        self.window.reset_planning_list_columns_action.trigger()
        self.window.reset_shds_columns_action.trigger()
        self.app.processEvents()
        self.window.toggle_theme()
        self.app.processEvents()

        self.assertTrue(directory.isColumnHidden(6))
        self.assertTrue(planning_list.isColumnHidden(8))
        self.assertTrue(shds.isColumnHidden(0))

    def test_reset_actions_clear_their_saved_state(self):
        directory = self.window.composition_directory_table
        planning_list = self.window.planning_list_table
        shds = self.window.staff_table

        directory.setColumnWidth(0, directory.columnWidth(0) + 11)
        planning_list.setColumnWidth(0, planning_list.columnWidth(0) + 11)
        shds.setColumnWidth(1, shds.columnWidth(1) + 11)
        self.app.processEvents()
        self.assertIsNotNone(self.settings.value("workspace/directory_header_state"))
        self.assertIsNotNone(self.settings.value("planning/list_header_state"))
        self.assertIsNotNone(self.settings.value("workspace/shds_header_state"))

        self.window.reset_directory_columns_action.trigger()
        self.window.reset_planning_list_columns_action.trigger()
        self.window.reset_shds_columns_action.trigger()
        self.app.processEvents()

        self.assertIsNone(self.settings.value("workspace/directory_header_state"))
        self.assertIsNone(self.settings.value("planning/list_header_state"))
        self.assertIsNone(self.settings.value("workspace/shds_header_state"))

    def test_calendar_columns_are_chronological_and_not_movable(self):
        days_header = self.window.planning_days_table.horizontalHeader()
        self.assertFalse(days_header.sectionsMovable())
        self.assertEqual(days_header.sectionResizeMode(0), QHeaderView.Fixed)
        first = self.window.planning_days_table.horizontalHeaderItem(0).text()
        self.assertTrue(first.startswith("1\n"))


if __name__ == "__main__":
    unittest.main()
