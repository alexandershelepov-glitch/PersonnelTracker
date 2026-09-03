from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import Database
from services import BatchConflictError, PersonnelService


def _employee_data(number: str, fio: str) -> dict:
    return {
        "fio": fio, "personnel_no": number, "department": "3 отдел", "position": "инспектор",
        "birth_date": None, "employment_date": None, "factual_address": "", "registration_address": "",
        "phone": "", "email": "", "schedule_type": "Не задан", "schedule_anchor_date": None,
        "employment_status": "Работает",
    }


def _event_data(start: str = "2026-09-10", end: str = "2026-09-12") -> dict:
    return {
        "event_type": "Командировка", "subtype": "", "start_date": start, "end_date": end,
        "location": "", "basis": "", "notes": "Группа",
    }


class BatchEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        self.svc = PersonnelService(self.db)
        self.emp1 = self.svc.save_employee(_employee_data("b-1", "Иванов Иван Иванович"))
        self.emp2 = self.svc.save_employee(_employee_data("b-2", "Петров Пётр Петрович"))
        self.emp3 = self.svc.save_employee(_employee_data("b-3", "Сидоров Алексей Сергеевич"))

    def tearDown(self):
        self.tmp.cleanup()

    def _all_events(self):
        return self.svc.list_events()

    # 24.1 migration -------------------------------------------------------
    def test_migration_adds_batch_id_and_keeps_old_rows_null(self):
        event_id = self.svc.add_event({**_event_data(), "employee_id": str(self.emp1)})
        migrated = Database(self.db.path)  # повторная инициализация = миграция
        with migrated.connect() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
            row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        self.assertIn("batch_id", columns)
        self.assertIsNone(row["batch_id"])
        self.assertEqual(migrated.get_setting("schema_version"), "6")

    # 24.2 creation ---------------------------------------------------------
    def test_batch_creation_assigns_one_batch_id_to_every_record(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2], _event_data())
        events = self._all_events()
        self.assertEqual(len(events), 2)
        self.assertTrue(batch_id)
        self.assertEqual({event["batch_id"] for event in events}, {batch_id})
        for event in events:
            self.assertEqual(event["event_type"], "Командировка")
            self.assertEqual(event["start_date"], "2026-09-10")
            self.assertEqual(event["end_date"], "2026-09-12")
            self.assertEqual(event["notes"], "Группа")

    def test_batch_creation_for_several_employees(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        self.assertEqual(len(self.svc.list_batch_events(batch_id)), 3)

    def test_every_batch_gets_a_new_uuid(self):
        first = self.svc.create_batch_events([self.emp1, self.emp2], _event_data())
        second = self.svc.create_batch_events([self.emp1, self.emp2], _event_data("2026-10-01", "2026-10-02"))
        self.assertNotEqual(first, second)

    def test_batch_requires_at_least_two_employees(self):
        for ids in ([], [self.emp1], [self.emp1, self.emp1]):
            with self.assertRaises(ValueError, msg=f"ids={ids}"):
                self.svc.create_batch_events(ids, _event_data())
        self.assertEqual(self._all_events(), [])

    def test_duplicate_employee_ids_are_deduplicated(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp1, self.emp2], _event_data())
        self.assertEqual(len(self.svc.list_batch_events(batch_id)), 2)

    # 24.3 overlap detection -----------------------------------------------
    def test_overlap_detection_cases(self):
        self.svc.add_event({**_event_data("2026-09-10", "2026-09-12"), "employee_id": str(self.emp1)})
        cases = [
            ("полное совпадение", "2026-09-10", "2026-09-12", True),
            ("начало внутри", "2026-09-11", "2026-09-15", True),
            ("конец внутри", "2026-09-05", "2026-09-11", True),
            ("новый перекрывает старый", "2026-09-01", "2026-09-20", True),
            ("старый внутри нового", "2026-09-10", "2026-09-10", True),
            ("граничное касание", "2026-09-12", "2026-09-14", True),
            ("без пересечения", "2026-09-13", "2026-09-14", False),
        ]
        for title, start, end, expected in cases:
            conflicts = self.svc.find_event_conflicts([self.emp1], start, end)
            self.assertEqual(bool(conflicts), expected, title)
            if expected:
                self.assertEqual(conflicts[0]["fio"], "Иванов Иван Иванович")
                self.assertEqual(conflicts[0]["start_date"], "2026-09-10")

    # 24.4 conflict blocks the whole batch ----------------------------------
    def test_conflict_in_one_employee_blocks_whole_batch(self):
        self.svc.add_event({**_event_data(), "employee_id": str(self.emp2)})
        with self.assertRaises(BatchConflictError) as ctx:
            self.svc.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        self.assertEqual(self._all_events(), self.svc.list_events())  # только исходная запись
        self.assertEqual(len(self._all_events()), 1)
        self.assertEqual(len(ctx.exception.conflicts), 1)
        self.assertEqual(ctx.exception.conflicts[0]["employee_id"], self.emp2)

    # 24.5 editing ----------------------------------------------------------
    def test_batch_update_changes_every_record(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        self.svc.update_batch_events(batch_id, _event_data("2026-09-15", "2026-09-16") | {"event_type": "Отпуск", "subtype": "очередной", "notes": "Изменено"})
        for event in self.svc.list_batch_events(batch_id):
            self.assertEqual(event["event_type"], "Отпуск")
            self.assertEqual(event["subtype"], "очередной")
            self.assertEqual(event["start_date"], "2026-09-15")
            self.assertEqual(event["end_date"], "2026-09-16")
            self.assertEqual(event["notes"], "Изменено")

    def test_batch_update_keeps_composition(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        before = sorted(int(e["employee_id"]) for e in self.svc.list_batch_events(batch_id))
        self.svc.update_batch_events(batch_id, _event_data("2026-09-20", "2026-09-21"))
        after = sorted(int(e["employee_id"]) for e in self.svc.list_batch_events(batch_id))
        self.assertEqual(before, after)

    def test_batch_update_does_not_conflict_with_itself(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2], _event_data())
        # Те же даты и тип — конфликта быть не должно.
        self.svc.update_batch_events(batch_id, _event_data())

    def test_batch_update_blocked_by_external_conflict(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2], _event_data())
        self.svc.add_event({**_event_data("2026-09-20", "2026-09-21"), "employee_id": str(self.emp1)})
        with self.assertRaises(BatchConflictError):
            self.svc.update_batch_events(batch_id, _event_data("2026-09-20", "2026-09-22"))
        for event in self.svc.list_batch_events(batch_id):
            self.assertEqual(event["start_date"], "2026-09-10")

    # 24.6 deletion ----------------------------------------------------------
    def test_batch_delete_removes_all_batch_records_only(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        keep = self.svc.add_event({**_event_data("2026-10-01", "2026-10-02"), "employee_id": str(self.emp1)})
        removed = self.svc.delete_batch_events(batch_id)
        self.assertEqual(removed, 3)
        self.assertEqual(self.svc.list_batch_events(batch_id), [])
        remaining = self._all_events()
        self.assertEqual([int(e["id"]) for e in remaining], [keep])

    # 24.7 rollback ----------------------------------------------------------
    def test_failed_insert_rolls_back_whole_batch(self):
        from contextlib import contextmanager

        class FailingConn:
            """Прокси соединения, падающий на второй вставке события."""
            def __init__(self, real):
                self._real, self.inserts = real, 0

            def execute(self, sql, parameters=()):
                if isinstance(sql, str) and sql.startswith("INSERT INTO events"):
                    self.inserts += 1
                    if self.inserts == 2:
                        raise sqlite3.OperationalError("сбой при второй вставке")
                return self._real.execute(sql, parameters)

            def __getattr__(self, name):
                return getattr(self._real, name)

        @contextmanager
        def failing_connect():
            raw = sqlite3.connect(self.db.path)
            raw.row_factory = sqlite3.Row
            conn = FailingConn(raw)
            try:
                yield conn
                raw.commit()
            except Exception:
                raw.rollback()
                raise
            finally:
                raw.close()

        self.svc.db.connect = failing_connect
        with self.assertRaises(sqlite3.OperationalError):
            self.svc.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        del self.svc.db.connect
        self.assertEqual(self._all_events(), [])

    # 24.8 single (legacy) events keep working --------------------------------
    def test_single_events_still_work(self):
        event_id = self.svc.add_event({**_event_data(), "employee_id": str(self.emp1)})
        self.assertIsNone(self.svc.get_event(event_id)["batch_id"])
        self.svc.update_event(event_id, self.emp1, _event_data("2026-09-11", "2026-09-13") | {"event_type": "Отпуск"})
        self.assertEqual(self.svc.get_event(event_id)["start_date"], "2026-09-11")
        self.svc.delete_event(event_id)
        self.assertIsNone(self.svc.get_event(event_id))

    def test_single_edit_and_delete_of_batch_record_rejected(self):
        batch_id = self.svc.create_batch_events([self.emp1, self.emp2], _event_data())
        event = self.svc.list_batch_events(batch_id)[0]
        with self.assertRaisesRegex(ValueError, "групповое назначение"):
            self.svc.update_event(int(event["id"]), int(event["employee_id"]), _event_data("2026-09-11", "2026-09-11"))
        with self.assertRaisesRegex(ValueError, "групповое назначение"):
            self.svc.delete_event(int(event["id"]))
        self.assertEqual(len(self.svc.list_batch_events(batch_id)), 2)


if __name__ == "__main__":
    unittest.main()
