from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database
from services import PersonnelService
from temporal_snapshot import TemporalPersonnelService
from today_state import TodayStateService


class TodayStateServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "personnel.db")
        self.people = PersonnelService(self.db)
        self.temporal = TemporalPersonnelService(self.db)
        self.service = TodayStateService(self.people, self.temporal)

    def tearDown(self):
        self.tmp.cleanup()

    def _employee(self, fio: str, number: str, schedule: str, anchor: str | None = None) -> int:
        employee_id = self.people.save_employee({
            "fio": fio,
            "personnel_no": number,
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "birth_date": "1990-01-01",
            "factual_address": "",
            "registration_address": "",
            "phone": "",
            "email": "",
            "employment_date": "2026-01-01",
            "schedule_type": schedule,
            "schedule_anchor_date": anchor,
            "employment_status": "Работает",
        })
        self.people.save_staff_unit({
            "unit_number": number,
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "employee_id": str(employee_id),
        })
        return employee_id

    def test_five_two_and_unknown_schedule_share_temporal_semantics(self):
        # 05.09.2026 is Saturday: 5/2 is a day off; unknown is not available.
        self._employee("Пять Два", "001", "5/2")
        self._employee("Без Графика", "002", "Не задан")
        snapshot = self.service.snapshot("2026-09-05")
        self.assertEqual(snapshot.staff, 2)
        self.assertEqual(snapshot.listed, 2)
        self.assertEqual(snapshot.present, 0)
        self.assertEqual(snapshot.absent, 1)
        self.assertEqual(snapshot.needs_check, 1)
        statuses = {row.fio: (row.status, row.availability) for row in snapshot.rows}
        self.assertEqual(statuses["Пять Два"], ("Выходной", "Недоступен"))
        self.assertEqual(statuses["Без Графика"], ("Работа / график не задан", "Требует проверки"))

    def test_event_overrides_work_schedule_and_keeps_event_details(self):
        employee_id = self._employee("Смена Рабочая", "003", "1/3", "2026-09-05")
        event_id = self.people.add_event({
            "employee_id": str(employee_id),
            "event_type": "Отпуск",
            "subtype": "очередной",
            "start_date": "2026-09-04",
            "end_date": "2026-09-07",
            "location": "",
            "basis": "приказ",
            "notes": "",
        })
        snapshot = self.service.snapshot("2026-09-05")
        row = snapshot.rows[0]
        self.assertEqual(row.status, "Отпуск")
        self.assertEqual(row.subtype, "очередной")
        self.assertEqual(row.availability, "Недоступен")
        self.assertEqual(row.event_id, event_id)
        self.assertEqual(row.start_date, "2026-09-04")
        self.assertEqual(row.end_date, "2026-09-07")

    def test_vacancy_is_counted_without_becoming_a_person_state(self):
        self._employee("Занятый", "004", "1/3", "2026-09-05")
        self.people.save_staff_unit({
            "unit_number": "005",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "employee_id": None,
        })
        snapshot = self.service.snapshot("2026-09-05")
        self.assertEqual(snapshot.staff, 2)
        self.assertEqual(snapshot.listed, 1)
        self.assertEqual(snapshot.vacant, 1)
        self.assertEqual(len(snapshot.rows), 1)
        self.assertTrue(snapshot.valid)


if __name__ == "__main__":
    unittest.main()
