from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import Database
from reports import (
    EMPTY_VALUE,
    UNASSIGNED_UNIT,
    PersonnelRosterReport,
    ReportExportError,
    format_report_date,
    render_csv,
    render_tsv,
    roster_headers,
    write_csv,
)
from services import PersonnelService


class PersonnelRosterReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "personnel.db")
        self.service = PersonnelService(self.db)
        self.report = PersonnelRosterReport(self.service)

    def tearDown(self):
        self.tmp.cleanup()

    def add_employee(self, fio: str, number: str, **overrides) -> int:
        payload = {
            "fio": fio,
            "personnel_no": number,
            "department": "карточка отдела",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "schedule_type": "1/3",
            "employment_status": "Работает",
        }
        payload.update(overrides)
        return self.service.save_employee(payload)

    def test_assigned_employee_uses_canonical_staff_unit_fields(self):
        employee_id = self.add_employee("Иванов Иван Иванович", "101")
        self.service.save_staff_unit({
            "unit_number": "12",
            "department": "ТУ 2",
            "section": "2 отделение",
            "group_name": "3 группа",
            "position": "старший инспектор",
            "employee_id": employee_id,
        })
        rows = self.report.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.fio, "Иванов Иван Иванович")
        self.assertEqual(row.personnel_no, "101")
        self.assertEqual(row.unit_number, "12")
        self.assertEqual(row.department, "ТУ 2")
        self.assertEqual(row.section, "2 отделение")
        self.assertEqual(row.group_name, "3 группа")
        self.assertEqual(row.position, "старший инспектор")
        self.assertEqual(row.schedule_type, "1/3")
        self.assertEqual(row.values(), (
            "Иванов Иван Иванович", "101", "12", "ТУ 2",
            "2 отделение", "3 группа", "старший инспектор", "1/3",
        ))

    def test_unassigned_active_employee_stays_in_report(self):
        self.add_employee("Петров Пётр Петрович", "202", schedule_type="5/2")
        row = self.report.rows()[0]
        self.assertEqual(row.unit_number, UNASSIGNED_UNIT)
        self.assertEqual(row.department, "карточка отдела")
        self.assertEqual(row.section, "1 отделение")
        self.assertEqual(row.group_name, "1 группа")
        self.assertEqual(row.position, "инспектор")
        self.assertEqual(row.schedule_type, "5/2")

    def test_archived_employee_is_excluded(self):
        assigned = self.add_employee("Назначенный Работник", "301")
        self.service.save_staff_unit({
            "unit_number": "5",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "2 группа",
            "position": "инспектор",
            "employee_id": assigned,
        })
        archived = self.add_employee("Архивный Работник", "302")
        self.service.archive_employee(archived)
        rows = self.report.rows()
        names = [row.fio for row in rows]
        self.assertEqual(names, ["Назначенный Работник"])

    def test_column_order_is_stable(self):
        self.assertEqual(roster_headers(), (
            "ФИО",
            "Табельный номер",
            "№ штатной единицы",
            "Подразделение",
            "Отделение",
            "Группа",
            "Должность",
            "График",
        ))
        self.add_employee("Сидоров Сидор Сидорович", "401")
        table = self.report.table()
        self.assertEqual(table.headers, roster_headers())
        self.assertEqual(len(table.rows[0]), 8)

    def test_empty_organisation_fields_use_placeholder(self):
        self.add_employee(
            "Без Организации",
            "501",
            department="",
            section="Не указано",
            group_name="",
            position="",
            schedule_type="",
        )
        row = self.report.rows()[0]
        self.assertEqual(row.unit_number, UNASSIGNED_UNIT)
        self.assertEqual(row.department, EMPTY_VALUE)
        self.assertEqual(row.position, EMPTY_VALUE)
        self.assertEqual(row.schedule_type, "Не задан")


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_csv_uses_utf8_bom_semicolon_headers_and_cyrillic(self):
        headers = roster_headers()
        rows = [(
            "Иванов Иван Иванович", "101", "12", "ТУ 2",
            "2 отделение", "3 группа", "старший инспектор", "1/3",
        )]
        target = write_csv(self.root / "roster.csv", headers, rows)
        raw = target.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        parsed = list(csv.reader(text.splitlines(), delimiter=";"))
        self.assertEqual(parsed[0], list(headers))
        self.assertEqual(parsed[1][0], "Иванов Иван Иванович")
        self.assertEqual(parsed[1][2], "12")
        self.assertNotIn(",", parsed[1][4])
        self.assertEqual(render_csv(headers, rows).splitlines()[0], ";".join(headers))

    def test_tsv_contains_tabs_header_and_cyrillic(self):
        headers = roster_headers()
        rows = [("Петров Пётр", "202", UNASSIGNED_UNIT, "3 отдел", "1 отделение", "1 группа", "инспектор", "5/2")]
        text = render_tsv(headers, rows)
        lines = text.split("\n")
        self.assertEqual(lines[0], "\t".join(headers))
        self.assertIn("\t", lines[1])
        self.assertEqual(lines[1].split("\t")[0], "Петров Пётр")
        self.assertEqual(lines[1].split("\t")[2], UNASSIGNED_UNIT)

    def test_report_date_helper_uses_user_format(self):
        self.assertEqual(format_report_date("2026-09-07"), "07.09.2026")
        self.assertEqual(format_report_date(""), "")

    def test_write_csv_wraps_directory_creation_errors(self):
        headers = roster_headers()
        rows = [("Иванов", "101", "12", "ТУ 2", "1 отделение", "1 группа", "инспектор", "1/3")]
        with patch.object(Path, "mkdir", side_effect=OSError("denied")):
            with self.assertRaises(ReportExportError):
                write_csv(self.root / "blocked" / "roster.csv", headers, rows)


if __name__ == "__main__":
    unittest.main()
