from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import Database
from services import PersonnelService
from temporal_snapshot import TemporalPersonnelService


class TemporalPersonnelServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.db = Database(self.data_dir / "personnel.db")
        self.people = PersonnelService(self.db)

        today = date.today().isoformat()
        self.assigned_id = self.people.save_employee({
            "fio": "Иванов Иван Иванович",
            "personnel_no": "1001",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "birth_date": "1990-01-01",
            "factual_address": "",
            "registration_address": "",
            "phone": "89000000000",
            "email": "",
            "employment_date": today,
            "schedule_type": "5/2",
            "schedule_anchor_date": None,
            "employment_status": "Работает",
        })
        self.unit_id = self.people.save_staff_unit({
            "unit_number": "001",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "employee_id": str(self.assigned_id),
        })

        self.unassigned_id = self.people.save_employee({
            "fio": "Петров Пётр Петрович",
            "personnel_no": "1002",
            "department": "3 отдел",
            "section": "2 отделение",
            "group_name": "2 группа",
            "position": "инспектор",
            "birth_date": "1991-01-01",
            "factual_address": "",
            "registration_address": "",
            "phone": "89000000001",
            "email": "",
            "employment_date": today,
            "schedule_type": "Не задан",
            "schedule_anchor_date": None,
            "employment_status": "Работает",
        })
        self.service = TemporalPersonnelService(self.db)
        self.today = date.today().isoformat()

    def tearDown(self):
        self.tmp.cleanup()

    def _row(self, employee_id: int):
        return next(row for row in self.service.states(self.today) if row.employee_id == employee_id)

    def test_snapshot_contains_assigned_and_unassigned_people(self):
        assigned = self._row(self.assigned_id)
        unassigned = self._row(self.unassigned_id)
        self.assertEqual(assigned.unit_number, "001")
        self.assertEqual(assigned.position, "инспектор")
        self.assertEqual(unassigned.unit_number, "ВНЕ ШДС")

    def test_event_overrides_schedule_and_marks_unavailable(self):
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
        row = self._row(self.assigned_id)
        self.assertEqual(row.status, "Отпуск")
        self.assertEqual(row.subtype, "очередной")
        self.assertEqual(row.availability, "Недоступен")
        self.assertEqual(row.source, "event")

    def test_five_two_schedule_uses_weekday(self):
        row = self._row(self.assigned_id)
        if date.today().weekday() < 5:
            self.assertEqual(row.status, "Работа")
            self.assertEqual(row.availability, "Доступен")
        else:
            self.assertEqual(row.status, "Выходной")
            self.assertEqual(row.availability, "Недоступен")

    def test_unknown_schedule_requires_review(self):
        row = self._row(self.unassigned_id)
        self.assertEqual(row.status, "Работа / график не задан")
        self.assertEqual(row.availability, "Требует проверки")

    def test_one_three_anchor_today_is_workday(self):
        person = dict(self.people.get_employee(self.unassigned_id))
        person["schedule_type"] = "1/3"
        person["schedule_anchor_date"] = self.today
        self.people.save_employee(person, self.unassigned_id)
        row = self._row(self.unassigned_id)
        self.assertEqual(row.status, "Работа")
        self.assertEqual(row.availability, "Доступен")

    def test_summary_balances_all_rows(self):
        summary = self.service.summary(self.today)
        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.assigned, 1)
        self.assertEqual(summary.unassigned, 1)
        self.assertEqual(
            summary.total,
            summary.available + summary.unavailable + summary.needs_check,
        )


if __name__ == "__main__":
    unittest.main()
