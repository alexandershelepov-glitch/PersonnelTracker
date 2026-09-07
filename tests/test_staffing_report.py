from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database
from services import PersonnelService
from staffing_report import (
    EMPTY_VALUE,
    OCCUPIED_STATUS,
    VACANCY_FIO,
    VACANT_STATUS,
    StaffingPlacementReport,
    staffing_headers,
)


class StaffingPlacementReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "personnel.db")
        self.service = PersonnelService(self.db)
        self.report = StaffingPlacementReport(self.service)

    def tearDown(self):
        self.tmp.cleanup()

    def add_employee(self, fio: str, number: str) -> int:
        return self.service.save_employee({
            "fio": fio,
            "personnel_no": number,
            "department": "карточка отдела",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "schedule_type": "1/3",
            "employment_status": "Работает",
        })

    def test_report_includes_occupied_and_vacant_units_in_natural_order(self):
        employee_id = self.add_employee("Иванов Иван Иванович", "101")
        self.service.save_staff_unit({
            "unit_number": "10",
            "department": "3 отдел",
            "section": "2 отделение",
            "group_name": "3 группа",
            "position": "инспектор",
            "employee_id": None,
        })
        self.service.save_staff_unit({
            "unit_number": "2",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "старший инспектор",
            "employee_id": employee_id,
        })

        rows = self.report.rows()
        self.assertEqual([row.unit_number for row in rows], ["2", "10"])

        occupied = rows[0]
        self.assertEqual(occupied.department, "3 отдел")
        self.assertEqual(occupied.section, "1 отделение")
        self.assertEqual(occupied.group_name, "1 группа")
        self.assertEqual(occupied.position, "старший инспектор")
        self.assertEqual(occupied.fio, "Иванов Иван Иванович")
        self.assertEqual(occupied.personnel_no, "101")
        self.assertEqual(occupied.schedule_type, "1/3")
        self.assertEqual(occupied.place_status, OCCUPIED_STATUS)

        vacant = rows[1]
        self.assertEqual(vacant.fio, VACANCY_FIO)
        self.assertEqual(vacant.personnel_no, EMPTY_VALUE)
        self.assertEqual(vacant.schedule_type, EMPTY_VALUE)
        self.assertEqual(vacant.place_status, VACANT_STATUS)

    def test_archived_assignee_leaves_vacancy_in_report(self):
        employee_id = self.add_employee("Петров Пётр Петрович", "202")
        self.service.save_staff_unit({
            "unit_number": "5",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "2 группа",
            "position": "инспектор",
            "employee_id": employee_id,
        })
        self.service.archive_employee(employee_id)

        row = self.report.rows()[0]
        self.assertEqual(row.unit_number, "5")
        self.assertEqual(row.fio, VACANCY_FIO)
        self.assertEqual(row.personnel_no, EMPTY_VALUE)
        self.assertEqual(row.place_status, VACANT_STATUS)

    def test_column_order_is_stable(self):
        self.assertEqual(staffing_headers(), (
            "№ штатной единицы",
            "Подразделение",
            "Отделение",
            "Группа",
            "Должность",
            "ФИО",
            "Табельный номер",
            "График",
            "Статус места",
        ))


if __name__ == "__main__":
    unittest.main()
