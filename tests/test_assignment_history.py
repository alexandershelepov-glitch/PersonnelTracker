from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from assignment_history import AssignmentHistoryService, ensure_assignment_history
from database import Database
from services import PersonnelService


class AssignmentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.db = Database(self.data_dir / "personnel.db")
        self.personnel = PersonnelService(self.db)
        self.employee_id = self.personnel.save_employee({
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
            "employment_date": "2020-01-01",
            "schedule_type": "5/2",
            "schedule_anchor_date": None,
            "employment_status": "Работает",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def create_unit(self, number: str = "1", employee_id: int | None = None, position: str = "инспектор") -> int:
        return self.personnel.save_staff_unit({
            "unit_number": number,
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": position,
            "employee_id": employee_id,
        })

    def test_existing_assignment_becomes_baseline_only_when_tracking_starts(self):
        unit_id = self.create_unit(employee_id=self.employee_id)
        with self.db.connect() as connection:
            exists_before = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='staff_assignments'"
            ).fetchone()
        self.assertIsNone(exists_before)

        started = ensure_assignment_history(self.db)
        history = AssignmentHistoryService(self.db)
        rows = history.list_history(self.employee_id)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["staff_unit_id"], unit_id)
        self.assertEqual(rows[0]["source"], "baseline")
        self.assertIsNone(rows[0]["end_at"])
        self.assertEqual(started, history.tracking_started_at)

    def test_assignment_and_release_are_recorded_automatically(self):
        ensure_assignment_history(self.db)
        unit_id = self.create_unit(employee_id=self.employee_id)
        history = AssignmentHistoryService(self.db)

        opened = history.list_history(self.employee_id)
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["source"], "assignment")
        self.assertIsNone(opened[0]["end_at"])

        unit = self.personnel.staff_unit(unit_id)
        self.personnel.save_staff_unit({
            "unit_number": unit["unit_number"],
            "department": unit["department"],
            "section": unit["section"],
            "group_name": unit["group_name"] or "",
            "position": unit["position"],
            "employee_id": None,
        }, unit_id)

        closed = history.list_history(self.employee_id)
        self.assertEqual(len(closed), 1)
        self.assertIsNotNone(closed[0]["end_at"])

    def test_changing_unit_details_splits_the_history_period(self):
        ensure_assignment_history(self.db)
        unit_id = self.create_unit(employee_id=self.employee_id)
        history = AssignmentHistoryService(self.db)

        self.personnel.save_staff_unit({
            "unit_number": "1",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "старший инспектор",
            "employee_id": self.employee_id,
        }, unit_id)

        rows = history.list_history(self.employee_id)
        self.assertEqual(len(rows), 2)
        current = next(row for row in rows if row["end_at"] is None)
        previous = next(row for row in rows if row["end_at"] is not None)
        self.assertEqual(current["position"], "старший инспектор")
        self.assertEqual(current["source"], "unit-change")
        self.assertEqual(previous["position"], "инспектор")

    def test_archiving_employee_closes_open_assignment(self):
        ensure_assignment_history(self.db)
        unit_id = self.create_unit(employee_id=self.employee_id)
        history = AssignmentHistoryService(self.db)

        self.personnel.archive_employee(self.employee_id, "Архив")

        rows = history.list_history(self.employee_id)
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0]["end_at"])
        self.assertIsNone(self.personnel.staff_unit(unit_id)["employee_id"])

    def test_snapshot_refuses_dates_before_tracking_started(self):
        self.create_unit(employee_id=self.employee_id)
        history = AssignmentHistoryService(self.db)
        yesterday = history.tracking_started_date - timedelta(days=1)

        with self.assertRaises(ValueError):
            history.snapshot(yesterday.isoformat())

        rows = history.snapshot(date.today().isoformat())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["employee_id"], self.employee_id)


if __name__ == "__main__":
    unittest.main()
