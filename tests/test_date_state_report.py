from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import Database
from date_state_report import (
    PersonnelDateStateReport,
    date_state_headers,
    default_date_state_csv_name,
)
from services import PersonnelService
from temporal_snapshot import TemporalPersonnelService


class PersonnelDateStateReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "personnel.db")
        self.people = PersonnelService(self.db)
        self.today = date.today().isoformat()

        self.assigned_id = self.people.save_employee({
            "fio": "Иванов Иван Иванович",
            "personnel_no": "101",
            "department": "карточка отдела",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "employment_date": self.today,
            "schedule_type": "5/2",
            "employment_status": "Работает",
        })
        self.people.save_staff_unit({
            "unit_number": "12",
            "department": "ТУ 2",
            "section": "2 отделение",
            "group_name": "3 группа",
            "position": "старший инспектор",
            "employee_id": self.assigned_id,
        })
        self.people.add_event({
            "employee_id": str(self.assigned_id),
            "event_type": "Отпуск",
            "subtype": "очередной",
            "start_date": self.today,
            "end_date": self.today,
            "location": "",
            "basis": "",
            "notes": "",
        })

        self.unassigned_id = self.people.save_employee({
            "fio": "Петров Пётр Петрович",
            "personnel_no": "202",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "2 группа",
            "position": "инспектор",
            "employment_date": self.today,
            "schedule_type": "Не задан",
            "employment_status": "Работает",
        })
        self.people.add_event({
            "employee_id": str(self.unassigned_id),
            "event_type": "Вновь принятые",
            "subtype": "",
            "start_date": self.today,
            "end_date": self.today,
            "location": "Учебный класс",
            "basis": "",
            "notes": "",
        })

        self.temporal = TemporalPersonnelService(self.db)
        self.report = PersonnelDateStateReport(self.temporal)

    def tearDown(self):
        self.tmp.cleanup()

    def test_headers_are_stable(self):
        self.assertEqual(date_state_headers(), (
            "ШЕ №", "Подразделение", "Отделение", "Группа", "Должность",
            "ФИО", "Табельный номер", "График", "Статус", "Место / объект", "Доступность",
        ))

    def test_report_uses_temporal_assignment_and_event_state(self):
        rows = self.report.rows(self.today)
        assigned = next(row for row in rows if row.fio == "Иванов Иван Иванович")
        unassigned = next(row for row in rows if row.fio == "Петров Пётр Петрович")

        self.assertEqual(assigned.unit_number, "12")
        self.assertEqual(assigned.department, "ТУ 2")
        self.assertEqual(assigned.section, "2 отделение")
        self.assertEqual(assigned.group_name, "3 группа")
        self.assertEqual(assigned.position, "старший инспектор")
        self.assertEqual(assigned.status, "Отпуск: очередной")
        self.assertEqual(assigned.availability, "Недоступен")

        self.assertEqual(unassigned.unit_number, "ВНЕ ШДС")
        self.assertEqual(unassigned.status, "Вновь принятые")
        self.assertEqual(unassigned.location, "Учебный класс")
        self.assertEqual(unassigned.availability, "Доступен")

    def test_unavailable_filter_uses_temporal_availability(self):
        rows = self.report.rows(self.today, unavailable_only=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].fio, "Иванов Иван Иванович")
        self.assertEqual(rows[0].availability, "Недоступен")

    def test_default_filename_reflects_date_and_filter(self):
        self.assertEqual(
            default_date_state_csv_name("2026-09-07"),
            "Состояние_личного_состава_2026-09-07.csv",
        )
        self.assertEqual(
            default_date_state_csv_name("2026-09-07", unavailable_only=True),
            "Недоступные_2026-09-07.csv",
        )


if __name__ == "__main__":
    unittest.main()
