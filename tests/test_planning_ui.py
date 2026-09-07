from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate, QSettings
from PySide6.QtWidgets import QApplication, QPushButton

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from employee_profile_ui import install_employee_profile_ui
from navigation_context import install_context_navigation
from planning_ui import install_planning_ui
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class PlanningUiTests(unittest.TestCase):
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
            install_employee_profile_ui,
            install_planning_ui,
            install_context_navigation,
        ):
            install(self.window)
        self.window.refresh_all()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _previous_month(self):
        page = self.window.pages.widget(2)
        previous = next(
            button for button in page.findChildren(QPushButton)
            if button.text() == "‹"
        )
        previous.click()
        self.app.processEvents()

    def test_planning_has_graph_and_list(self):
        tabs = self.window.planning_tabs
        self.assertEqual(tabs.count(), 2)
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())], ["График", "Список"])
        self.assertEqual(tabs.currentIndex(), 0)
        self.assertTrue(self.window.planning_legacy.isHidden())

    def test_russian_month_weekdays_and_display_dates(self):
        self.assertIn("Сентябрь", self.window.planning_month_label.text())
        first_header = self.window.planning_days_table.horizontalHeaderItem(0).text().lower()
        self.assertIn("вт", first_header)

        self._previous_month()
        self.assertIn("Август", self.window.planning_month_label.text())
        event_list = self.window.planning_list_table
        self.assertGreater(event_list.rowCount(), 0)
        self.assertRegex(event_list.item(0, 3).text(), r"^\d{2}\.\d{2}\.\d{4}$")
        self.assertRegex(event_list.item(0, 4).text(), r"^\d{2}\.\d{2}\.\d{4}$")

    def test_month_graph_and_list_use_same_events(self):
        # Test execution date is September 2026; demo events are in August.
        self._previous_month()
        grid = self.window.planning_days_table
        event_list = self.window.planning_list_table
        self.assertEqual(grid.columnCount(), 31)
        self.assertEqual(grid.rowCount(), 4)
        self.assertEqual(event_list.rowCount(), 2)

        graph_event_ids = set()
        for row in range(grid.rowCount()):
            for column in range(grid.columnCount()):
                item = grid.item(row, column)
                if item is not None and item.data(0x0100) is not None:
                    graph_event_ids.add(int(item.data(0x0100)))
        list_event_ids = {
            int(event_list.item(row, 8).text())
            for row in range(event_list.rowCount())
        }
        self.assertEqual(graph_event_ids, list_event_ids)

    def test_empty_day_prefills_employee_and_date(self):
        self._previous_month()
        employee_id = int(self.window.planning_people_table.item(0, 0).data(0x0100))
        chosen = QDate(2026, 8, 15)
        with patch("ui.EventDialog") as editor:
            dialog = editor.return_value
            dialog.exec.return_value = 0
            self.window.open_new_planning_event(employee_id, chosen)
            editor.assert_called_once_with(self.window.service, parent=self.window, employee_id=employee_id)
            dialog.start.setDate.assert_called_once_with(chosen)
            dialog.end.setDate.assert_called_once_with(chosen)

    def test_filters_apply_to_graph_and_list(self):
        self._previous_month()
        self.window.planning_section.setCurrentText("1 отделение")
        self.app.processEvents()
        self.assertEqual(self.window.planning_people_table.rowCount(), 2)
        # The demo vacation belongs to one of the first-section employees.
        self.assertEqual(self.window.planning_list_table.rowCount(), 1)

    def test_future_month_is_allowed_for_planning(self):
        page = self.window.pages.widget(2)
        next_button = next(
            button for button in page.findChildren(QPushButton)
            if button.text() == "›"
        )
        next_button.click()
        next_button.click()
        self.app.processEvents()
        self.assertGreater(self.window.planning_days_table.columnCount(), 0)


if __name__ == "__main__":
    unittest.main()
