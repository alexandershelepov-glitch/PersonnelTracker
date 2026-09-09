from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton

from assignment_history import AssignmentHistoryService
from assignment_history_report import AssignmentHistoryReport, assignment_history_headers
from assignment_history_report_ui import install_assignment_history_report_ui
from reports_ui import install_reports_ui
from ui import MainWindow


class AssignmentHistoryReportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        self.window.assignment_history = AssignmentHistoryService(self.window.db)
        self.employee_id = self.window.service.save_employee({
            "fio": "Иванов Иван Иванович",
            "personnel_no": "101",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "schedule_type": "1/3",
            "employment_status": "Работает",
        })
        self.window.service.save_staff_unit({
            "unit_number": "001",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "employee_id": self.employee_id,
        })
        install_reports_ui(self.window)
        install_assignment_history_report_ui(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_install_is_idempotent_and_adds_entry(self):
        install_assignment_history_report_ui(self.window)
        box = self.window.findChild(QGroupBox, "reportsGroup")
        buttons = [button.text() for button in box.findChildren(QPushButton)]
        self.assertEqual(buttons.count("История назначений"), 1)
        self.assertTrue(callable(self.window.open_assignment_history_report))

    def test_table_matches_history_report(self):
        view = self.window.assignment_history_report_view_type()
        expected = AssignmentHistoryReport(self.window.assignment_history).rows()
        self.assertEqual(view.table.columnCount(), 10)
        self.assertEqual(
            [view.table.horizontalHeaderItem(i).text() for i in range(10)],
            list(assignment_history_headers()),
        )
        self.assertEqual(view.table.rowCount(), len(expected))
        self.assertGreaterEqual(view.table.rowCount(), 1)
        self.assertEqual(view.table.item(0, 3).text(), expected[0].fio)
        view.deleteLater()
        self.app.processEvents()

    def test_employee_filter_and_refresh_do_not_duplicate(self):
        view = self.window.assignment_history_report_view_type()
        index = view.employee.findData(self.employee_id)
        self.assertGreaterEqual(index, 0)
        view.employee.setCurrentIndex(index)
        view.refresh()
        expected = AssignmentHistoryReport(self.window.assignment_history).rows(self.employee_id)
        self.assertEqual(view.table.rowCount(), len(expected))
        view.refresh()
        self.assertEqual(view.table.rowCount(), len(expected))
        view.deleteLater()
        self.app.processEvents()

    def test_export_csv_without_dialog(self):
        view = self.window.assignment_history_report_view_type()
        destination = Path(self.tmp.name) / "history.csv"
        result = view.export_csv(destination=destination)
        self.assertEqual(result, destination.resolve())
        self.assertTrue(destination.exists())
        content = destination.read_text(encoding="utf-8-sig")
        self.assertIn("ФИО", content)
        self.assertIn("Иванов Иван Иванович", content)
        view.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
