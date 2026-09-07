from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from employee_profile_ui import install_employee_profile_ui
from interface_polish import install_interface_polish
from manual_team_ui import install_manual_team_ui
from navigation_context import install_context_navigation
from planning_ui import install_planning_ui
from planning_usability import install_planning_usability
from semi_auto_team_ui import install_semi_auto_team_ui
from service_page_scroll import install_service_page_scroll
from tab_theme_fix import install_tab_theme_fix
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class FinalAuditPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(cls.tmp.name) / "settings.ini"), QSettings.IniFormat)
        cls.settings_patch = patch("ui.QSettings", return_value=settings)
        cls.settings_patch.start()
        cls.window = MainWindow(Path(cls.tmp.name) / "personnel.db")
        positions = ("Инспектор", "Старший инспектор", "Начальник группы")
        started = time.perf_counter()
        for index in range(90):
            employee_id = cls.window.service.save_employee({
                "fio": f"Сотрудник Тестовый {index + 1:03d}",
                "personnel_no": f"T-{index + 1:03d}",
                "department": "3 отдел",
                "section": "1 отделение" if index % 2 == 0 else "2 отделение",
                "group_name": f"{index % 6 + 1} группа",
                "position": positions[index % len(positions)],
                "schedule_type": "5/2",
                "employment_status": "Работает",
            })
            cls.window.service.save_staff_unit({
                "unit_number": str(index + 1),
                "department": "3 отдел",
                "section": "1 отделение" if index % 2 == 0 else "2 отделение",
                "group_name": f"{index % 6 + 1} группа",
                "position": positions[index % len(positions)],
                "employee_id": str(employee_id),
            })
        for installer in (
            install_backup_features,
            install_csv_features,
            install_assignment_history_features,
            install_temporal_snapshot_features,
            install_service_page_scroll,
            install_workflow_ui,
            install_composition_ui,
            install_manual_team_ui,
            install_semi_auto_team_ui,
            install_employee_profile_ui,
            install_planning_ui,
            install_planning_usability,
            install_context_navigation,
            install_interface_polish,
            install_tab_theme_fix,
        ):
            installer(cls.window)
        cls.window.refresh_all()
        cls.elapsed = time.perf_counter() - started
        cls.window.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.settings_patch.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.window.composition_search.clear()
        self.window.manual_team_search.clear()
        self.window.planning_search.clear()
        self.window.composition_reset_filters.click()
        self.window.manual_team_reset_filters.click()
        self.window.semi_auto_team_reset_filters.click()
        self.window.planning_reset_filters.click()
        self.app.processEvents()

    def test_large_roster_remains_scrollable_and_aligned(self):
        sidebar_versions = [
            label.text()
            for label in self.window.findChildren(QLabel)
            if label.objectName() == "appSubtitle" and label.text().startswith("v")
        ]
        self.assertEqual(sidebar_versions, ["v0.8.3"])
        self.assertEqual(self.window.composition_directory_table.rowCount(), 90)
        self.assertEqual(self.window.manual_team_table.rowCount(), 90)
        self.assertEqual(self.window.planning_people_table.rowCount(), 90)
        self.assertEqual(self.window.planning_days_table.rowCount(), 90)
        self.assertEqual(
            self.window.planning_people_table.verticalHeader().defaultSectionSize(),
            self.window.planning_days_table.verticalHeader().defaultSectionSize(),
        )
        self.assertGreater(self.window.composition_directory_table.verticalScrollBar().maximum(), 0)
        self.assertGreater(self.window.manual_team_table.verticalScrollBar().maximum(), 0)
        self.assertLess(self.elapsed, 8.0)

    def test_minimum_window_leaves_calendar_usable(self):
        self.window.resize(760, 520)
        self.window._select_page(2, record_history=False)
        self.window.planning_tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.assertEqual(self.window.width(), 760)
        self.assertGreaterEqual(self.window.planning_days_table.viewport().width(), 200)

    def test_planning_splitter_state_is_saved(self):
        self.window._select_page(2, record_history=False)
        self.window.planning_tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.window.planning_splitter.moveSplitter(300, 1)
        self.app.processEvents()
        self.assertIsNotNone(self.window.settings.value("planning/splitter_state"))

    def test_filter_status_and_reset_are_explicit(self):
        cases = (
            (self.window.composition_department, self.window.composition_filter_status, self.window.composition_reset_filters),
            (self.window.manual_team_department, self.window.manual_team_filter_status, self.window.manual_team_reset_filters),
            (self.window.semi_auto_team_department, self.window.semi_auto_team_filter_status, self.window.semi_auto_team_reset_filters),
            (self.window.planning_department, self.window.planning_filter_status, self.window.planning_reset_filters),
        )
        for combo, status, reset in cases:
            combo.setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(status.text(), "Фильтры применены")
            self.assertTrue(reset.isEnabled())
            reset.click()
            self.app.processEvents()
            self.assertEqual(combo.currentIndex(), 0)
            self.assertEqual(status.text(), "")

    def test_empty_states_replace_blank_tables(self):
        self.window.composition_search.setText("нет-такого-сотрудника")
        self.window.manual_team_search.setText("нет-такого-сотрудника")
        self.window.planning_search.setText("нет-такого-события")
        self.window._select_page(0, record_history=False)
        self.window.composition_tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.assertTrue(self.window.composition_empty_state.isVisible())
        self.assertFalse(self.window.composition_directory_table.isVisible())
        self.window.composition_tabs.setCurrentIndex(1)
        self.window.manual_team_mode_tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.assertTrue(self.window.manual_team_empty_state.isVisible())
        self.assertFalse(self.window.manual_team_table.isVisible())
        self.window._select_page(2, record_history=False)
        self.window.planning_tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertTrue(self.window.planning_list_empty.isVisible())
        self.assertFalse(self.window.planning_list_table.isVisible())

    def test_find_shortcut_focuses_visible_working_search(self):
        self.window._select_page(0, record_history=False)
        self.window.composition_tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.window._interface_find_shortcut.activated.emit()
        self.app.processEvents()
        self.assertTrue(self.window.composition_search.hasFocus())

        self.window._select_page(2, record_history=False)
        self.window.planning_tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.window._interface_find_shortcut.activated.emit()
        self.app.processEvents()
        self.assertTrue(self.window.planning_search.hasFocus())

    def test_long_cells_have_full_text_tooltips(self):
        table = self.window.composition_directory_table
        self.assertEqual(table.item(0, 1).toolTip(), table.item(0, 1).text())
        manual = self.window.manual_team_table
        self.assertEqual(manual.item(0, 2).toolTip(), manual.item(0, 2).text())

    def test_semi_auto_event_reuses_batch_dialog_and_selected_date(self):
        self.window.propose_semi_auto_team()
        selected = self.window.semi_auto_team_selected_ids()
        self.assertEqual(len(selected), 2)
        with patch("ui.BatchEventDialog") as editor:
            dialog = editor.return_value
            dialog.exec.return_value = 0
            self.window.create_semi_auto_team_event()
            editor.assert_called_once_with(self.window.service, self.window, preselected=selected)
            chosen = self.window.semi_auto_team_date.date()
            dialog.start.setDate.assert_called_once_with(chosen)
            dialog.end.setDate.assert_called_once_with(chosen)


if __name__ == "__main__":
    unittest.main()
