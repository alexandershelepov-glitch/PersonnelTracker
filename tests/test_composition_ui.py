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
from navigation_context import install_context_navigation
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class CompositionUiTests(unittest.TestCase):
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
            install_context_navigation,
        ):
            install(self.window)
        # Demo data is inserted after MainWindow's initial refresh, so force one
        # shared refresh before assertions about the reused SHDS widgets.
        self.window.refresh_all()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_composition_has_three_workflow_tabs(self):
        tabs = self.window.composition_tabs
        self.assertEqual(tabs.count(), 3)
        self.assertEqual(
            [tabs.tabText(index) for index in range(tabs.count())],
            ["Справочник", "Сформировать команду", "ШДС"],
        )
        self.window.nav_group.button(0).click()
        self.app.processEvents()
        self.assertEqual(tabs.currentIndex(), 0)
        page_title = next(
            label for label in self.window.pages.widget(0).findChildren(QLabel)
            if label.objectName() == "pageTitle"
        )
        self.assertEqual(page_title.text(), "Состав")

    def test_directory_search_filters_and_copy(self):
        table = self.window.composition_directory_table
        self.window.nav_group.button(0).click()
        self.app.processEvents()
        self.assertEqual(table.rowCount(), 4)

        self.window.composition_search.setText("Петров")
        self.app.processEvents()
        self.assertEqual(table.rowCount(), 1)
        self.assertIn("Петров", table.item(0, 0).text())

        self.window.composition_search.clear()
        self.window.composition_section.setCurrentText("1 отделение")
        self.app.processEvents()
        self.assertEqual(table.rowCount(), 2)

        self.window.composition_section.setCurrentText("Все")
        self.app.processEvents()
        table.selectRow(0)
        self.window.composition_copy_mode.setCurrentText("ФИО + табельный №")
        expected_fio = table.item(0, 0).text()
        self.window.copy_composition_selection()
        copied = QApplication.clipboard().text()
        self.assertIn(expected_fio, copied)
        self.assertIn("таб. №", copied)

    def test_existing_shds_widgets_are_reused_inside_shds_tab(self):
        shds = self.window.composition_tabs.widget(2)
        self.assertTrue(shds.isAncestorOf(self.window.staff_table))
        self.assertTrue(shds.isAncestorOf(self.window.metric_staff.parentWidget()))
        self.assertGreaterEqual(self.window.staff_table.rowCount(), 1)

    def test_today_team_action_opens_team_tab_with_back_context(self):
        self.window._select_page(
            self.window.pages.indexOf(self.window.today_page), record_history=False
        )
        self.window.today_page.team.click()
        self.app.processEvents()
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.assertEqual(self.window.composition_tabs.currentIndex(), 1)
        self.assertTrue(self.window._context_back_buttons[0].isVisible())
        self.window.navigate_back()
        self.assertIs(self.window.pages.currentWidget(), self.window.today_page)

    def test_sidebar_composition_is_root_and_defaults_to_directory(self):
        self.window.composition_tabs.setCurrentIndex(2)
        self.window.nav_group.button(0).click()
        self.app.processEvents()
        self.assertEqual(self.window.composition_tabs.currentIndex(), 0)
        self.assertFalse(self.window._context_back_buttons[0].isVisible())


if __name__ == "__main__":
    unittest.main()
