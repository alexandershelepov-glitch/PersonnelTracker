from __future__ import annotations

import tempfile
import unittest
import sqlite3
from datetime import date
from pathlib import Path

from database import Database
from services import PersonnelService, calculate_age


class PersonnelServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        self.svc = PersonnelService(self.db)
        self.emp = self.svc.save_employee({
            "fio": "Иванов Иван Иванович", "personnel_no": "1", "department": "3 отдел", "position": "инспектор",
            "birth_date": "1990-01-01", "factual_address": "", "registration_address": "", "phone": "", "email": "",
            "employment_date": "2020-01-01", "schedule_type": "1/3", "schedule_anchor_date": "2026-08-24", "employment_status": "Работает",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_schedule_13(self):
        self.assertTrue(self.svc.is_workday_13(date(2026, 8, 24), date(2026, 8, 24)))
        self.assertFalse(self.svc.is_workday_13(date(2026, 8, 25), date(2026, 8, 24)))
        self.assertTrue(self.svc.is_workday_13(date(2026, 8, 28), date(2026, 8, 24)))

    def test_event_overrides_schedule(self):
        self.svc.add_event({
            "employee_id": str(self.emp), "event_type": "Отпуск", "subtype": "очередной",
            "start_date": "2026-08-24", "end_date": "2026-08-31", "location": "", "basis": "", "notes": "",
        })
        statuses = self.svc.daily_statuses("2026-08-24")
        self.assertEqual(statuses[0].status, "Отпуск")
        self.assertEqual(statuses[0].subtype, "очередной")

    def test_overlapping_event_rejected(self):
        self.svc.add_event({
            "employee_id": str(self.emp), "event_type": "Отпуск", "subtype": "очередной",
            "start_date": "2026-08-24", "end_date": "2026-08-31", "location": "", "basis": "", "notes": "",
        })
        with self.assertRaises(ValueError):
            self.svc.add_event({
                "employee_id": str(self.emp), "event_type": "Сдача медкомиссии", "subtype": "",
                "start_date": "2026-08-25", "end_date": "2026-08-25", "location": "", "basis": "", "notes": "",
            })

    def test_history_record_can_be_updated_and_deleted(self):
        self.svc.add_medical_check(self.emp, "2026-08-24", "Первичная запись")
        record = self.svc.list_simple_history("medical_checks", self.emp)[0]
        self.svc.update_history_record(
            "medical_checks", int(record["id"]), self.emp,
            {"check_date": "2026-08-25", "notes": "Уточнено"},
        )
        updated = self.svc.get_history_record("medical_checks", int(record["id"]), self.emp)
        self.assertEqual(updated["check_date"], "2026-08-25")
        self.assertEqual(updated["notes"], "Уточнено")
        self.svc.delete_history_record("medical_checks", int(record["id"]), self.emp)
        self.assertEqual(self.svc.list_simple_history("medical_checks", self.emp), [])

    def test_event_can_be_updated_without_changing_schedule_logic(self):
        event_id = self.svc.add_event({
            "employee_id": str(self.emp), "event_type": "Отпуск", "subtype": "очередной",
            "start_date": "2026-08-24", "end_date": "2026-08-25", "location": "", "basis": "", "notes": "",
        })
        self.svc.update_event(event_id, self.emp, {
            "event_type": "Больничный", "subtype": "амбулаторно",
            "start_date": "2026-08-24", "end_date": "2026-08-26", "location": "", "basis": "Листок", "notes": "",
        })
        status = self.svc.daily_statuses("2026-08-24")[0]
        self.assertEqual(status.status, "Больничный")
        self.assertEqual(status.subtype, "амбулаторно")

    def test_empty_employee_dates_are_stored_as_empty(self):
        employee_id = self.svc.save_employee({
            "fio": "Без Дат", "personnel_no": "2", "department": "", "position": "",
            "birth_date": None, "employment_date": None, "factual_address": "",
            "registration_address": "", "phone": "", "email": "",
            "schedule_type": "Не задан", "schedule_anchor_date": None, "employment_status": "Работает",
        })
        employee = self.svc.get_employee(employee_id)
        self.assertIsNone(employee["birth_date"])
        self.assertIsNone(employee["employment_date"])

    def test_weapon_crud_uses_name_and_number(self):
        weapon_id = self.svc.add_weapon(self.emp, "Пистолет Макарова", "ПМ-12345")
        weapon = self.svc.get_history_record("weapons", weapon_id, self.emp)
        self.assertEqual(weapon["weapon_type"], "Пистолет Макарова")
        self.assertEqual(weapon["serial_number"], "ПМ-12345")
        self.svc.update_weapon(weapon_id, self.emp, "Пистолет Ярыгина", "ПЯ-777")
        weapon = self.svc.get_history_record("weapons", weapon_id, self.emp)
        self.assertEqual((weapon["weapon_type"], weapon["serial_number"]), ("Пистолет Ярыгина", "ПЯ-777"))
        self.svc.delete_history_record("weapons", weapon_id, self.emp)
        self.assertEqual(self.svc.list_simple_history("weapons", self.emp), [])

    def test_photo_path_is_saved_and_loaded(self):
        source = Path(self.tmp.name) / "source.ppm"
        # A minimal valid 1×1 image supported by Qt without an image plugin.
        source.write_bytes(b"P3\n1 1\n255\n255 0 0\n")
        relative_path = self.svc.save_photo(self.emp, source)
        employee = self.svc.get_employee(self.emp)
        self.assertEqual(employee["photo_path"], relative_path)
        self.assertTrue(self.svc.photo_file(relative_path).exists())
        self.svc.remove_photo(self.emp)
        self.assertIsNone(self.svc.get_employee(self.emp)["photo_path"])

    def test_existing_v02_database_is_migrated(self):
        old_path = Path(self.tmp.name) / "v02.db"
        conn = sqlite3.connect(old_path)
        conn.executescript("""
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fio TEXT NOT NULL,
                personnel_no TEXT NOT NULL UNIQUE, department TEXT NOT NULL DEFAULT '',
                position TEXT NOT NULL DEFAULT '', birth_date TEXT,
                factual_address TEXT NOT NULL DEFAULT '', registration_address TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', employment_date TEXT,
                schedule_type TEXT NOT NULL DEFAULT 'Не задан', schedule_anchor_date TEXT,
                employment_status TEXT NOT NULL DEFAULT 'Работает', archive_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE weapons (
                id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
                weapon_type TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL,
                assignment_date TEXT, removal_date TEXT, basis TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("INSERT INTO employees(fio, personnel_no) VALUES ('Старый работник', 'old-1')")
        conn.execute("INSERT INTO weapons(employee_id, weapon_type, model, serial_number, assignment_date) VALUES (1, 'Пистолет', 'ПМ', '111', '2026-01-01')")
        conn.commit(); conn.close()
        migrated = Database(old_path)
        with migrated.connect() as check:
            columns = {row["name"] for row in check.execute("PRAGMA table_info(employees)")}
            weapon = check.execute("SELECT * FROM weapons WHERE id=1").fetchone()
        self.assertIn("photo_path", columns)
        self.assertEqual(weapon["model"], "ПМ")
        self.assertEqual(migrated.get_setting("schema_version"), "5")

    def test_staff_unit_and_section_metrics(self):
        second = self.svc.save_employee({
            "fio": "Петров Пётр", "personnel_no": "staff-2", "department": "3 отдел", "section": "2 отделение", "position": "инспектор",
            "birth_date": None, "employment_date": None, "factual_address": "", "registration_address": "", "phone": "", "email": "",
            "schedule_type": "Не задан", "schedule_anchor_date": None, "employment_status": "Работает",
        })
        one = self.svc.save_staff_unit({"unit_number": "1", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": self.emp})
        self.svc.save_staff_unit({"unit_number": "2", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": None})
        self.svc.save_staff_unit({"unit_number": "3", "department": "3 отдел", "section": "2 отделение", "position": "инспектор", "employee_id": second})
        with self.assertRaises(ValueError):
            self.svc.save_staff_unit({"unit_number": "4", "department": "3 отдел", "section": "2 отделение", "position": "инспектор", "employee_id": self.emp})
        summary = self.svc.staff_metrics("2026-08-24")
        self.assertEqual(summary["total"], {"staff": 3, "listed": 2, "vacant": 1, "absent": 0, "present": 2})
        self.assertTrue(summary["valid"])
        self.assertEqual(self.svc.staff_unit(one)["section"], "1 отделение")

    def test_v03_migration_adds_neutral_section_and_staff_unit(self):
        path = Path(self.tmp.name) / "v03.db"
        old = Database(path)
        service = PersonnelService(old)
        employee_id = service.save_employee({"fio": "До миграции", "personnel_no": "m-1", "department": "3 отдел", "position": "инспектор", "birth_date": None, "employment_date": None, "factual_address": "", "registration_address": "", "phone": "", "email": "", "schedule_type": "Не задан", "schedule_anchor_date": None, "employment_status": "Работает"})
        # Simulate v0.3 storage by removing the v0.4-only structure in a copy.
        with old.connect() as conn:
            conn.execute("DROP TABLE staff_units")
            conn.execute("UPDATE settings SET value='3' WHERE key='schema_version'")
        migrated = Database(path)
        self.assertEqual(migrated.get_setting("schema_version"), "5")
        self.assertEqual(PersonnelService(migrated).get_employee(employee_id)["section"], "Не указано")
        self.assertEqual(len(PersonnelService(migrated).list_staff_units()), 1)

    def test_staff_model_is_the_only_source_for_metrics_and_copy(self):
        # The employee from setUp has no unit and must not affect the totals.
        other = self.svc.save_employee({"fio": "В составе", "personnel_no": "in-unit", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "birth_date": None, "employment_date": None, "factual_address": "", "registration_address": "", "phone": "", "email": "", "schedule_type": "Не задан", "schedule_anchor_date": None, "employment_status": "Работает"})
        self.svc.save_staff_unit({"unit_number": "10", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": other})
        self.svc.save_staff_unit({"unit_number": "11", "department": "3 отдел", "section": "2 отделение", "position": "инспектор", "employee_id": None})
        metrics = self.svc.staff_metrics("2026-08-24")["total"]
        self.assertEqual(metrics, {"staff": 2, "listed": 1, "vacant": 1, "absent": 0, "present": 1})
        self.assertEqual(len(self.svc.unassigned_active_employees()), 1)
        text = self.svc.render_daily_text("2026-08-24")
        self.assertTrue(text.startswith("24.08.2026"))
        self.assertIn("По штату - 2", text)

    def test_empty_weapon_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Укажите наименование"):
            self.svc.add_weapon(self.emp, "", "")

    def test_staff_unit_and_employee_service_data_stay_synced(self):
        unit = self.svc.save_staff_unit({"unit_number": "sync", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": self.emp})
        self.svc.save_staff_unit({"unit_number": "sync", "department": "3 отдел", "section": "2 отделение", "position": "старший инспектор", "employee_id": self.emp}, unit)
        employee = self.svc.get_employee(self.emp)
        self.assertEqual((employee["effective_section"], employee["effective_position"]), ("2 отделение", "старший инспектор"))
        self.svc.save_employee({"fio": employee["fio"], "personnel_no": employee["personnel_no"], "department": "3 отдел", "section": "Руководство", "position": "начальник", "birth_date": None, "employment_date": None, "factual_address": "", "registration_address": "", "phone": "", "email": "", "schedule_type": "Не задан", "schedule_anchor_date": None, "employment_status": "Работает"}, self.emp)
        # Once assigned, the staff unit is the organisational source of truth.
        self.assertEqual(self.svc.staff_unit(unit)["section"], "2 отделение")

    def test_new_employee_does_not_create_staff_unit(self):
        self.assertEqual(self.svc.list_staff_units(), [])
        reopened = PersonnelService(Database(self.db.path))
        self.assertEqual(reopened.list_staff_units(), [])

    def test_employee_can_be_assigned_to_existing_vacancy(self):
        unit = self.svc.save_staff_unit({"unit_number": "1", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": None})
        self.svc.save_staff_unit({"unit_number": "1", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": self.emp}, unit)
        self.assertEqual(self.svc.staff_unit(unit)["employee_id"], self.emp)

    def test_unit_number_is_unique_and_vacant_unit_can_be_deleted(self):
        unit = self.svc.save_staff_unit({"unit_number": "101", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": None})
        with self.assertRaises(sqlite3.IntegrityError):
            self.svc.save_staff_unit({"unit_number": "101", "department": "3 отдел", "section": "2 отделение", "position": "инспектор", "employee_id": None})
        self.svc.delete_staff_unit(unit)
        self.assertIsNone(self.svc.staff_unit(unit))

    def test_occupied_unit_cannot_be_deleted(self):
        unit = self.svc.save_staff_unit({"unit_number": "102", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": self.emp})
        with self.assertRaisesRegex(ValueError, "занята работником"):
            self.svc.delete_staff_unit(unit)

    def test_dismissal_releases_unit_and_archives_employee(self):
        unit = self.svc.save_staff_unit({"unit_number": "103", "department": "3 отдел", "section": "1 отделение", "group_name": "2 группа", "position": "инспектор", "employee_id": self.emp})
        self.svc.archive_employee(self.emp, "Уволен", "2026-08-20")
        employee = self.svc.get_employee(self.emp)
        self.assertEqual(employee["archive_date"], "2026-08-20")
        self.assertIsNone(self.svc.staff_unit(unit)["employee_id"])
        self.assertEqual(len(self.svc.archived_employees()), 1)
        self.assertEqual(self.svc.staff_metrics("2026-08-24")["total"]["listed"], 0)

    def test_group_is_saved_and_canonical(self):
        self.svc.save_staff_unit({"unit_number": "104", "department": "3 отдел", "section": "1 отделение", "group_name": "3 группа", "position": "инспектор", "employee_id": self.emp})
        self.assertEqual(self.svc.get_employee(self.emp)["effective_group"], "3 группа")

    def test_age_natural_sort_and_authorized_headcount_do_not_affect_metrics(self):
        self.assertEqual(calculate_age("2000-08-25", date(2026, 8, 25)), 26)
        for number in ("М-10", "М-2", "М-1"):
            self.svc.save_staff_unit({"unit_number": number, "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": None})
        self.assertEqual([row["unit_number"] for row in self.svc.list_staff_units()], ["М-1", "М-2", "М-10"])
        before = self.svc.staff_metrics("2026-08-24")["total"]
        self.db.set_setting("authorized_headcount", "999")
        self.assertEqual(self.svc.staff_metrics("2026-08-24")["total"], before)

    def test_event_cannot_be_reassigned_to_another_employee(self):
        other = self.svc.save_employee({"fio": "Другой", "personnel_no": "other", "department": "", "section": "Не указано", "position": "", "birth_date": None, "employment_date": None, "factual_address": "", "registration_address": "", "phone": "", "email": "", "schedule_type": "Не задан", "schedule_anchor_date": None, "employment_status": "Работает"})
        event = self.svc.add_event({"employee_id": str(self.emp), "event_type": "Отпуск", "subtype": "", "start_date": "2026-08-24", "end_date": "2026-08-24", "location": "", "basis": "", "notes": ""})
        with self.assertRaisesRegex(ValueError, "Нельзя изменить работника"):
            self.svc.update_event(event, other, {"event_type": "Отпуск", "subtype": "", "start_date": "2026-08-24", "end_date": "2026-08-24", "location": "", "basis": "", "notes": ""})
        self.assertEqual(self.svc.get_event(event)["employee_id"], self.emp)

    def test_state_on_date_and_weapon_text(self):
        self.svc.save_staff_unit({"unit_number": "105", "department": "3 отдел", "section": "1 отделение", "group_name": "1 группа", "position": "инспектор", "employee_id": self.emp})
        self.svc.add_weapon(self.emp, "АК-205", "123456")
        self.svc.add_weapon(self.emp, "ПМ", "АБ7890")
        self.svc.add_event({"employee_id": str(self.emp), "event_type": "Отпуск", "subtype": "очередной", "start_date": "2026-08-24", "end_date": "2026-08-24", "location": "", "basis": "", "notes": ""})
        state = self.svc.staff_state_on_date("2026-08-24")[0]
        self.assertEqual((state["state"], state["reason"]), ("Отсутствует", "Отпуск: очередной"))
        self.assertEqual(self.svc.weapon_summary(self.emp), "АК-205, ПМ")
        self.assertEqual(self.svc.weapon_text(self.emp), "АК-205 №123456; ПМ №АБ7890")

    def test_not_specified_section_is_counted_separately(self):
        unit = self.svc.save_staff_unit({"unit_number": "old", "department": "3 отдел", "section": "Руководство", "position": "инспектор", "employee_id": None})
        self.svc.save_staff_unit({"unit_number": "old", "department": "3 отдел", "section": "Не указано", "position": "инспектор", "employee_id": None}, unit)
        metrics = self.svc.staff_metrics("2026-08-24")
        self.assertEqual(metrics["by_section"]["Не указано"]["staff"], 1)
        self.assertEqual(sum(item["staff"] for item in metrics["by_section"].values()), metrics["total"]["staff"])

    def test_empty_staff_unit_number_rejected(self):
        base = {"department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": None}
        for bad in ("", "   ", None):
            with self.assertRaises(ValueError, msg=f"unit_number={bad!r}"):
                self.svc.save_staff_unit({**base, "unit_number": bad})
        unit = self.svc.save_staff_unit({**base, "unit_number": "7"})
        with self.assertRaises(ValueError):
            self.svc.save_staff_unit({**base, "unit_number": "   "}, unit)

    def test_natural_sort_of_legacy_unit_numbers(self):
        for number in ("М-10", "М-2", "М-1", "10", "2"):
            self.svc.save_staff_unit({"unit_number": number, "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": None})
        ordered = [row["unit_number"] for row in self.svc.list_staff_units()]
        self.assertEqual(ordered, ["2", "10", "М-1", "М-2", "М-10"])

    def test_group_comes_from_staff_unit(self):
        unit = self.svc.save_staff_unit({"unit_number": "21", "department": "3 отдел", "section": "1 отделение", "group_name": "2 группа", "position": "инспектор", "employee_id": self.emp})
        self.assertEqual(self.svc.get_employee(self.emp)["effective_group"], "2 группа")
        self.svc.save_staff_unit({"unit_number": "21", "department": "3 отдел", "section": "1 отделение", "group_name": "4 группа", "position": "инспектор", "employee_id": self.emp}, unit)
        self.assertEqual(self.svc.get_employee(self.emp)["effective_group"], "4 группа")
        self.svc.save_staff_unit({"unit_number": "21", "department": "3 отдел", "section": "Руководство", "group_name": "", "position": "инспектор", "employee_id": self.emp}, unit)
        self.assertEqual(self.svc.get_employee(self.emp)["effective_group"], "—")

    def test_filter_values_cover_all_visible_columns(self):
        self.svc.save_staff_unit({"unit_number": "31", "department": "3 отдел", "section": "1 отделение", "group_name": "1 группа", "position": "инспектор", "employee_id": self.emp})
        self.svc.add_medical_check(self.emp, "2026-08-20")
        self.svc.add_periodic_check(self.emp, "2026-08-21", "годен")
        headers = ["№", "Отдел", "Отделение", "Группа", "Должность", "ФИО", "Таб. №", "Дата рождения", "Возраст", "Телефон", "Вооружение", "Email", "Дата приёма", "Последняя МК", "Последняя ПП", "График"]
        for column in headers:
            values = self.svc.staff_filter_values(column)
            self.assertTrue(values, f"Фильтр колонки {column!r} пуст")
        self.assertEqual(self.svc.staff_filter_values("Последняя МК"), ["2026-08-20"])
        self.assertEqual(self.svc.staff_filter_values("Последняя ПП"), ["2026-08-21"])
        self.assertEqual(self.svc.staff_filter_values("График"), ["1/3"])
        self.assertEqual(self.svc.staff_filter_values("Группа"), ["1 группа"])

    def test_filters_apply_to_new_columns_and_use_placeholder(self):
        self.svc.save_staff_unit({"unit_number": "41", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": self.emp})
        self.svc.save_staff_unit({"unit_number": "42", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": None})
        filtered = self.svc.list_staff_units(filters={"График": {"1/3"}})
        self.assertEqual([row["unit_number"] for row in filtered], ["41"])
        placeholder = self.svc.staff_filter_values("Телефон")
        self.assertIn("—", placeholder)  # пустые значения дают единый маркер
        filtered = self.svc.list_staff_units(filters={"Телефон": {"—"}})
        self.assertEqual([row["unit_number"] for row in filtered], ["41", "42"])

    def test_metrics_unchanged_by_audit_fixes(self):
        self.svc.save_staff_unit({"unit_number": "51", "department": "3 отдел", "section": "1 отделение", "position": "инспектор", "employee_id": self.emp})
        self.svc.save_staff_unit({"unit_number": "52", "department": "3 отдел", "section": "2 отделение", "position": "инспектор", "employee_id": None})
        metrics = self.svc.staff_metrics("2026-08-24")
        self.assertEqual(metrics["total"], {"staff": 2, "listed": 1, "vacant": 1, "absent": 0, "present": 1})
        self.assertTrue(metrics["valid"])


if __name__ == "__main__":
    unittest.main()
