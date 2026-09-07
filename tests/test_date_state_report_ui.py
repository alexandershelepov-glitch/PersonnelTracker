from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton

from date_state_report_ui import install_date_state_report_ui
from reports_ui import install_reports_ui
from temporal_snapshot import TemporalPersonnelService
from ui import MainWindow


class PersonnelDateStateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        self.window.temporal_personnel = TemporalPersonnelService(self.window.db)
        install_reports_ui(self.window)
        install_date_state_report_ui(self.window)
        self.window.show()
        self.app.processEvents()
        self.today = date.today().isoformat()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _fill_sample(self) -> None:
        unavailable_id = self.window.service.save_employee({
            "fio": "Иванов Иван Иванович",
            "personnel_no": "101",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "employment_date": self.today,
            "schedule_type": "5/2",
            "employment_status": "Работает",
        })
        self.window.service.add_event({
            "employee_id": str(unavailable_id),
            "event_type": "Отпуск",
            "subtype": "очередной",
            "start_date": self.today,
            "end_date": self.today,
            "location": "",
            "basis": "",
            "notes": "",
        })
        available_id = self.window.service.save_employee({
            "fio": "Петров Пётр Петрович",
            "personnel_no": "202",
            "department": "3 отдел",
            "section": "2 отделение",
            "group_name": "2 группа",
            "position": "инспектор",
            "employment_date": self.today,
            "schedule_type": "Не задан",
            "employment_status": "Работает",
        })
        self.window.service.add_event({
            "employee_id": str(available_id),
            "event_type": "Вновь принятые",
            "subtype": "",
            "start_date": self.today,
            "end_date": self.today,
            "location": "Учебный класс",
            "basis": "",
            "notes": "",
        })

    def test_reports_group_gets_single_date_state_entry_and_screen(self):
        install_date_state_report_ui(self.window)
        box = self.window.findChild(QGroupBox, "reportsGroup")
        buttons = [button.text() for button in box.findChildren(QPushButton)]
        self.assertEqual(buttons.count("Состояние на дату"), 1)
        self.assertTrue(callable(self.window.open_date_state_report))

        view = self.window.date_state_report_view_type()
        self.assertEqual(view.table.columnCount(), 11)
        self.assertEqual(
            [view.table.horizontalHeaderItem(index).text() for index in range(11)],
            ["ШЕ №", "Подразделение", "Отделение", "Группа", "Должность",
             "ФИО", "Табельный номер", "График", "Статус", "Место / объект", "Доступность"],
        )
        view.deleteLater()
        self.app.processEvents()

    def test_unavailable_filter_reduces_table_without_duplicates(self):
        self._fill_sample()
        view = self.window.date_state_report_view_type()
        self.assertEqual(view.table.rowCount(), 2)
        index = view.filter.findText("Недоступные")
        self.assertGreaterEqual(index, 0)
        view.filter.setCurrentIndex(index)
        self.app.processEvents()
        self.assertEqual(view.table.rowCount(), 1)
        self.assertEqual(view.table.item(0, 5).text(), "Иванов Иван Иванович")
        self.assertEqual(view.table.item(0, 10).text(), "Недоступен")
        view.refresh()
        self.app.processEvents()
        self.assertEqual(view.table.rowCount(), 1)
        view.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
