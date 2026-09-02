from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import Database


class V04ToV05MigrationTests(unittest.TestCase):
    def test_real_v04_events_table_migrates_before_batch_index_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy_v04.db"

            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO settings(key, value) VALUES('schema_version', '4');

                CREATE TABLE employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fio TEXT NOT NULL,
                    personnel_no TEXT NOT NULL UNIQUE,
                    department TEXT NOT NULL DEFAULT '',
                    position TEXT NOT NULL DEFAULT '',
                    section TEXT NOT NULL DEFAULT 'Не указано',
                    group_name TEXT,
                    birth_date TEXT,
                    factual_address TEXT NOT NULL DEFAULT '',
                    registration_address TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    employment_date TEXT,
                    schedule_type TEXT NOT NULL DEFAULT 'Не задан',
                    schedule_anchor_date TEXT,
                    employment_status TEXT NOT NULL DEFAULT 'Работает',
                    archive_date TEXT,
                    photo_path TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    subtype TEXT NOT NULL DEFAULT '',
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    basis TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(end_date>=start_date)
                );

                INSERT INTO employees(fio, personnel_no, department, position)
                VALUES('Иванов Иван Иванович', 'legacy-1', '3 отдел', 'Инспектор');

                INSERT INTO events(employee_id, event_type, start_date, end_date, notes)
                VALUES(1, 'Отпуск', '2026-08-01', '2026-08-14', 'Старая запись v0.4');
                """
            )
            conn.commit()
            conn.close()

            db = Database(db_path)

            with db.connect() as migrated:
                columns = {row["name"] for row in migrated.execute("PRAGMA table_info(events)")}
                indexes = {row["name"] for row in migrated.execute("PRAGMA index_list(events)")}
                row = migrated.execute("SELECT event_type, notes, batch_id FROM events WHERE id=1").fetchone()

            self.assertIn("batch_id", columns)
            self.assertIn("idx_events_batch", indexes)
            self.assertEqual(row["event_type"], "Отпуск")
            self.assertEqual(row["notes"], "Старая запись v0.4")
            self.assertIsNone(row["batch_id"])
            self.assertEqual(db.get_setting("schema_version"), "5")

            # Repeated initialization must remain safe and idempotent.
            Database(db_path)
            with db.connect() as migrated_again:
                self.assertEqual(
                    migrated_again.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                    1,
                )
                indexes_again = {row["name"] for row in migrated_again.execute("PRAGMA index_list(events)")}
            self.assertIn("idx_events_batch", indexes_again)


if __name__ == "__main__":
    unittest.main()
