"""Тесты полей «Образование» и «Номер удостоверения» (дополнение к v0.6).

Покрывают создание/чтение/редактирование через сервисный слой и безопасную
миграцию старой БД без новых колонок (включая повторный запуск)."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import Database
from services import PersonnelService


def _base_payload() -> dict:
    return {
        "fio": "Петров Пётр Петрович", "personnel_no": "777", "department": "3 отдел",
        "position": "инспектор", "birth_date": "1990-05-12", "factual_address": "",
        "registration_address": "", "phone": "", "email": "",
        "employment_date": "2020-01-01", "schedule_type": "Не задан",
        "schedule_anchor_date": None, "employment_status": "Работает",
    }


class EmployeeProfileFieldsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        self.svc = PersonnelService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_read_update_education_and_certificate(self):
        payload = _base_payload()
        payload["education"] = "высшее"
        payload["certificate_number"] = "УД-123456"
        employee_id = self.svc.save_employee(payload)

        person = self.svc.get_employee(employee_id)
        self.assertEqual(person["education"], "высшее")
        self.assertEqual(person["certificate_number"], "УД-123456")

        updated = _base_payload()
        updated["education"] = "среднее профессиональное"
        updated["certificate_number"] = "УД-999"
        self.svc.save_employee(updated, employee_id)

        person = self.svc.get_employee(employee_id)
        self.assertEqual(person["education"], "среднее профессиональное")
        self.assertEqual(person["certificate_number"], "УД-999")

    def test_empty_values_are_allowed(self):
        employee_id = self.svc.save_employee(_base_payload())
        person = self.svc.get_employee(employee_id)
        self.assertIn(person["education"], ("", None))
        self.assertIn(person["certificate_number"], ("", None))


class LegacyDatabaseMigrationTests(unittest.TestCase):
    """Старая БД (схема v0.5, без education/certificate_number)."""

    LEGACY_SCHEMA = """
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    INSERT INTO settings(key, value) VALUES('schema_version', '5');
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fio TEXT NOT NULL, personnel_no TEXT NOT NULL UNIQUE,
        department TEXT NOT NULL DEFAULT '', position TEXT NOT NULL DEFAULT '',
        section TEXT NOT NULL DEFAULT 'Не указано', group_name TEXT,
        birth_date TEXT, factual_address TEXT NOT NULL DEFAULT '', registration_address TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', employment_date TEXT,
        schedule_type TEXT NOT NULL DEFAULT 'Не задан', schedule_anchor_date TEXT,
        employment_status TEXT NOT NULL DEFAULT 'Работает', archive_date TEXT,
        photo_path TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE staff_units (
        id INTEGER PRIMARY KEY AUTOINCREMENT, unit_number TEXT NOT NULL UNIQUE, department TEXT NOT NULL DEFAULT '',
        section TEXT NOT NULL, group_name TEXT, position TEXT NOT NULL,
        employee_id INTEGER UNIQUE REFERENCES employees(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE medical_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, check_date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE periodic_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, check_date TEXT NOT NULL, result TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE trainings (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, specialty TEXT NOT NULL, training_date TEXT NOT NULL, order_ref TEXT NOT NULL DEFAULT '', certificate TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE weapons (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, weapon_type TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL, assignment_date TEXT, removal_date TEXT, basis TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, event_type TEXT NOT NULL, subtype TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL, end_date TEXT NOT NULL, location TEXT NOT NULL DEFAULT '', basis TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', batch_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, CHECK(end_date>=start_date));
    """

    def _build_legacy_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.executescript(self.LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO employees(fio, personnel_no, department, position, birth_date) "
            "VALUES('Старов Стар Старыч', '42', '1 отдел', 'инспектор', '1980-02-02')"
        )
        conn.commit()
        conn.close()

    def test_legacy_db_opens_and_migrates_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            self._build_legacy_db(db_path)

            # 4–5. Старая БД открывается, новые колонки добавляются автоматически.
            db = Database(db_path)
            with db.connect() as conn:
                cols = {row["name"] for row in conn.execute("PRAGMA table_info(employees)")}
            self.assertIn("education", cols)
            self.assertIn("certificate_number", cols)

            # 6. Прежние данные сохранились, новые поля пустые.
            svc = PersonnelService(db)
            person = svc.get_employee(1)
            self.assertEqual(person["fio"], "Старов Стар Старыч")
            self.assertEqual(person["personnel_no"], "42")
            self.assertEqual(person["birth_date"], "1980-02-02")
            self.assertEqual(person["education"], "")
            self.assertEqual(person["certificate_number"], "")

            # Сервисный слой работает поверх мигрированной базы.
            svc.save_employee({**_base_payload(), "fio": "Старов Стар Старыч", "personnel_no": "42",
                               "education": "иное", "certificate_number": "X-1"}, 1)
            person = svc.get_employee(1)
            self.assertEqual(person["fio"], "Старов Стар Старыч")
            self.assertEqual(person["education"], "иное")
            self.assertEqual(person["certificate_number"], "X-1")

            # 7. Повторная миграция (переоткрытие БД) не вызывает ошибку.
            db2 = Database(db_path)
            svc2 = PersonnelService(db2)
            person = svc2.get_employee(1)
            self.assertEqual(person["fio"], "Старов Стар Старыч")
            self.assertEqual(person["education"], "иное")
            with db2.connect() as conn:
                version = conn.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
            self.assertEqual(version["value"], str(Database.CURRENT_VERSION))


if __name__ == "__main__":
    unittest.main()
