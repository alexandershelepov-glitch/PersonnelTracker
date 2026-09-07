from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QGroupBox

from reports import PersonnelRosterReport
from reports_ui import install_reports_ui
from ui import MainWindow


class PersonnelRosterUiTests(unittest.TestCase):
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
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _fill_sample(self) -> None:
        assigned = self.window.service.save_employee({
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
            "unit_number": "12",
            "department": "ТУ 2",
            "section": "2 отделение",
            "group_name": "3 группа",
            "position": "старший инспектор",
            "employee_id": assigned,
        })
        self.window.service.save_employee({
            "fio": "Петров Пётр Петрович",
            "personnel_no": "202",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "2 группа",
            "position": "инспектор",
            "schedule_type": "5/2",
            "employment_status": "Работает",
        })

    def test_reports_section_and_roster_screen_are_created(self):
        groups = [box.title() for box in self.window.findChildren(QGroupBox)]
        self.assertIn("Отчёты", groups)
        self.assertTrue(callable(self.window.open_personnel_roster_report))
        view = self.window.personnel_roster_view_type()
        self.assertEqual(view.table.columnCount(), 8)
        self.assertEqual(
            [view.table.horizontalHeaderItem(index).text() for index in range(8)],
            ["ФИО", "Табельный номер", "№ штатной единицы", "Подразделение",
             "Отделение", "Группа", "Должность", "График"],
        )
        view.deleteLater()
        self.app.processEvents()

    def test_table_matches_facade_and_refresh_does_not_duplicate(self):
        self._fill_sample()
        view = self.window.personnel_roster_view_type()
        expected = PersonnelRosterReport(self.window.service).rows()
        self.assertEqual(view.table.rowCount(), len(expected))
        self.assertEqual(view.table.rowCount(), 2)
        self.assertEqual(view.table.item(0, 0).text(), expected[0].fio)
        self.assertEqual(view.table.item(0, 2).text(), expected[0].unit_number)
        view.refresh()
        self.app.processEvents()
        self.assertEqual(view.table.rowCount(), len(expected))
        self.assertEqual(view.table.rowCount(), 2)
        view.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
