from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from csv_data import CsvDataError, CsvEmployeeManager
from database import Database
from services import PersonnelService


class CsvEmployeeManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "personnel.db")
        self.manager = CsvEmployeeManager(self.db)
        self.service = PersonnelService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def write_csv(self, name: str, text: str, encoding: str = "utf-8-sig") -> Path:
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return path

    def add_existing(self, fio: str = "Иванов Иван Иванович", number: str = "100") -> int:
        return self.service.save_employee({
            "fio": fio,
            "personnel_no": number,
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "birth_date": "1990-01-01",
            "phone": "+70000000000",
            "employment_date": "2020-01-01",
            "schedule_type": "Не задан",
            "employment_status": "Работает",
        })

    def test_preview_maps_russian_headers_and_normalizes_dates(self):
        source = self.write_csv(
            "people.csv",
            "ФИО;Таб. №;Отдел;Отделение;Группа;Должность;Дата рождения;Телефон;Дата приёма;График;Дата рабочей смены\n"
            "Петров Пётр Петрович;200;3 отдел;1 отделение;2 группа;инспектор;12.05.1992;+79990000000;01.02.2021;1/3;03.09.2026\n",
        )
        preview = self.manager.preview_file(source)
        self.assertEqual(len(preview.rows), 1)
        row = preview.rows[0]
        self.assertEqual(row.status, "ready")
        self.assertEqual(row.data["personnel_no"], "200")
        self.assertEqual(row.data["birth_date"], "1992-05-12")
        self.assertEqual(row.data["employment_date"], "2021-02-01")
        self.assertEqual(row.data["schedule_anchor_date"], "2026-09-03")
        self.assertEqual(row.data["schedule_type"], "1/3")

    def test_cp1251_and_extra_column_are_supported(self):
        source = self.write_csv(
            "legacy.csv",
            "ФИО;Табельный номер;Должность;Лишняя колонка\nСидоров Сидор Сидорович;201;старший инспектор;не используется\n",
            encoding="cp1251",
        )
        preview = self.manager.preview_file(source)
        self.assertEqual(preview.rows[0].status, "ready")
        self.assertIn("Лишняя колонка", preview.ignored_headers)

    def test_existing_number_is_blocked_and_existing_name_is_warning(self):
        self.add_existing()
        source = self.write_csv(
            "duplicates.csv",
            "ФИО;Табельный номер;Должность\n"
            "Другой Работник;100;инспектор\n"
            "Иванов Иван Иванович;101;инспектор\n",
        )
        preview = self.manager.preview_file(source)
        self.assertEqual(preview.rows[0].status, "error")
        self.assertFalse(preview.rows[0].importable)
        self.assertEqual(preview.rows[1].status, "warning")
        self.assertTrue(preview.rows[1].importable)

    def test_import_is_transactional_and_does_not_create_staff_units(self):
        source = self.write_csv(
            "import.csv",
            "ФИО;Табельный номер;Отдел;Отделение;Группа;Должность\n"
            "Первый Работник;301;3 отдел;1 отделение;1 группа;инспектор\n"
            "Второй Работник;302;3 отдел;2 отделение;2 группа;старший инспектор\n",
        )
        preview = self.manager.preview_file(source)
        count = self.manager.import_rows(preview.rows)
        self.assertEqual(count, 2)
        with self.db.connect() as conn:
            employees = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
            units = conn.execute("SELECT COUNT(*) FROM staff_units").fetchone()[0]
            second = conn.execute("SELECT section,group_name,position FROM employees WHERE personnel_no='302'").fetchone()
        self.assertEqual(employees, 2)
        self.assertEqual(units, 0)
        self.assertEqual(second["section"], "2 отделение")
        self.assertEqual(second["group_name"], "2 группа")
        self.assertEqual(second["position"], "старший инспектор")

    def test_import_rechecks_duplicates_before_writing_any_row(self):
        source = self.write_csv(
            "race.csv",
            "ФИО;Табельный номер\nПервый;401\nВторой;402\n",
        )
        preview = self.manager.preview_file(source)
        self.add_existing("Появился после предпросмотра", "402")
        with self.assertRaises(CsvDataError):
            self.manager.import_rows(preview.rows)
        with self.db.connect() as conn:
            numbers = [row[0] for row in conn.execute("SELECT personnel_no FROM employees ORDER BY personnel_no").fetchall()]
        self.assertEqual(numbers, ["402"])

    def test_export_uses_excel_friendly_utf8_bom_semicolon_and_effective_staff_data(self):
        employee_id = self.add_existing("Экспорт Экспорт Экспорт", "501")
        self.service.save_staff_unit({
            "unit_number": "10",
            "department": "ТУ 2",
            "section": "2 отделение",
            "group_name": "3 группа",
            "position": "старший инспектор",
            "employee_id": employee_id,
        })
        target = self.manager.export_active(self.root / "export.csv")
        raw = target.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(text.splitlines(), delimiter=";"))
        self.assertEqual(rows[0][0:6], ["ФИО", "Табельный номер", "Отдел", "Отделение", "Группа", "Должность"])
        self.assertEqual(rows[1][0], "Экспорт Экспорт Экспорт")
        self.assertEqual(rows[1][2:6], ["ТУ 2", "2 отделение", "3 группа", "старший инспектор"])


if __name__ == "__main__":
    unittest.main()
