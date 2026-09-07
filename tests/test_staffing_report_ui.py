from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton

from reports_ui import install_reports_ui
from staffing_report import StaffingPlacementReport
from staffing_report_ui import install_staffing_report_ui
from ui import MainWindow


class StaffingPlacementUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        install_reports_ui(self.window)
        install_staffing_report_ui(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _fill_sample(self) -> None:
        employee_id = self.window.service.save_employee({
            "fio": "Иванов Иван Иванович",
            "personnel_no": "101",
            "department": "карточка отдела",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "schedule_type": "1/3",
            "employment_status": "Работает",
        })
        self.window.service.save_staff_unit({
            "unit_number": "1",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "старший инспектор",
            "employee_id": employee_id,
        })
        self.window.service.save_staff_unit({
            "unit_number": "2",
            "department": "3 отдел",
            "section": "2 отделение",
            "group_name": "3 группа",
            "position": "инспектор",
            "employee_id": None,
        })

    def test_reports_group_gets_single_staffing_entry_and_screen(self):
        install_staffing_report_ui(self.window)
        box = self.window.findChild(QGroupBox, "reportsGroup")
        buttons = [button.text() for button in box.findChildren(QPushButton)]
        self.assertEqual(buttons.count("Штатная расстановка"), 1)
        self.assertTrue(callable(self.window.open_staffing_placement_report))

        view = self.window.staffing_placement_view_type()
        self.assertEqual(view.table.columnCount(), 9)
        self.assertEqual(
            [view.table.horizontalHeaderItem(index).text() for index in range(9)],
            ["№ штатной единицы", "Подразделение", "Отделение", "Группа", "Должность",
             "ФИО", "Табельный номер", "График", "Статус места"],
        )
        view.deleteLater()
        self.app.processEvents()

    def test_table_matches_report_and_refresh_does_not_duplicate(self):
        self._fill_sample()
        view = self.window.staffing_placement_view_type()
        expected = StaffingPlacementReport(self.window.service).rows()
        self.assertEqual(view.table.rowCount(), len(expected))
        self.assertEqual(view.table.rowCount(), 2)
        self.assertEqual(view.table.item(0, 0).text(), expected[0].unit_number)
        self.assertEqual(view.table.item(0, 5).text(), expected[0].fio)
        self.assertEqual(view.table.item(1, 8).text(), expected[1].place_status)
        view.refresh()
        self.app.processEvents()
        self.assertEqual(view.table.rowCount(), len(expected))
        self.assertEqual(view.table.rowCount(), 2)
        view.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
