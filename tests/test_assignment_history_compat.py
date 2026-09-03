from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assignment_history import AssignmentHistoryService
from assignment_history_compat import repair_legacy_assignment_history
from database import Database
from services import PersonnelService


class AssignmentHistoryCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.db = Database(self.data_dir / "personnel.db")
        self.service = PersonnelService(self.db)
        self.employee_id = self.service.save_employee({
            "fio": "Иванов Иван Иванович",
            "personnel_no": "1001",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "birth_date": "1990-01-01",
            "factual_address": "",
            "registration_address": "",
            "phone": "",
            "email": "",
            "employment_date": "2020-01-01",
            "schedule_type": "5/2",
            "schedule_anchor_date": None,
            "employment_status": "Работает",
        })
        self.unit_id = self.service.save_staff_unit({
            "unit_number": "1",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "employee_id": self.employee_id,
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_incompatible_table_is_preserved_then_v08_history_starts_cleanly(self):
        with self.db.connect() as connection:
            connection.execute(
                """
                CREATE TABLE staff_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER,
                    staff_unit_id INTEGER,
                    start_date TEXT,
                    end_date TEXT,
                    note TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO staff_assignments(employee_id,staff_unit_id,start_date,note) VALUES(?,?,?,?)",
                (self.employee_id, self.unit_id, "2025-01-01", "legacy row"),
            )
            connection.execute(
                "INSERT INTO settings(key,value) VALUES('history_tracking_started_at','2025-01-01T00:00:00')"
            )

        legacy_name = repair_legacy_assignment_history(self.db)
        self.assertIsNotNone(legacy_name)
        with self.db.connect() as connection:
            preserved = connection.execute(
                f'SELECT note FROM "{legacy_name}"'
            ).fetchone()
            self.assertEqual(preserved["note"], "legacy row")
            marker = connection.execute(
                "SELECT value FROM settings WHERE key='history_tracking_started_at'"
            ).fetchone()
            self.assertIsNone(marker)
            current = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='staff_assignments'"
            ).fetchone()
            self.assertIsNone(current)

        history = AssignmentHistoryService(self.db)
        rows = history.list_history()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "baseline")
        self.assertEqual(rows[0]["employee_id"], self.employee_id)

    def test_compatible_v08_table_is_left_untouched(self):
        history = AssignmentHistoryService(self.db)
        before = history.summary().total_records
        self.assertIsNone(repair_legacy_assignment_history(self.db))
        after = history.summary().total_records
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
