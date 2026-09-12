from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from assignment_history import AssignmentHistoryService
from assignment_history_report import (
    CURRENT_ASSIGNMENT,
    SOURCE_LABELS,
    AssignmentHistoryReport,
    assignment_history_headers,
    default_assignment_history_csv_name,
)
from database import Database


class AssignmentHistoryReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "personnel.db")
        self.history = AssignmentHistoryService(self.db)
        self.report = AssignmentHistoryReport(self.history)
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO employees(fio, personnel_no, department, position, schedule_type, employment_status)
                   VALUES('Иванов Иван Иванович','101','3 отдел','инспектор','1/3','Работает')"""
            )
            self.employee_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """INSERT INTO staff_assignments(
                    employee_id,staff_unit_id,employee_fio,employee_personnel_no,unit_number,
                    department,section,group_name,position,start_at,end_at,source
                ) VALUES(?,NULL,'Иванов Иван Иванович','101','001','3 отдел','1 отделение','1 группа',
                         'инспектор','2026-09-01T08:30:00','2026-09-05T17:15:00','assignment')""",
                (self.employee_id,),
            )
            conn.execute(
                """INSERT INTO staff_assignments(
                    employee_id,staff_unit_id,employee_fio,employee_personnel_no,unit_number,
                    department,section,group_name,position,start_at,end_at,source
                ) VALUES(?,NULL,'Иванов Иван Иванович','101','002','3 отдел','2 отделение',NULL,
                         'старший инспектор','2026-09-05T17:15:00',NULL,'unit-change')""",
                (self.employee_id,),
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_headers_are_stable(self):
        self.assertEqual(assignment_history_headers(), (
            "С", "До", "Табельный номер", "ФИО", "№ штатной единицы",
            "Подразделение", "Отделение", "Группа", "Должность", "Запись",
        ))

    def test_rows_use_historical_values_and_labels(self):
        rows = self.report.rows()
        self.assertEqual(len(rows), 2)
        newest = rows[0]
        self.assertEqual(newest.unit_number, "002")
        self.assertEqual(newest.position, "старший инспектор")
        self.assertEqual(newest.end_at, CURRENT_ASSIGNMENT)
        self.assertEqual(newest.group_name, "—")
        self.assertEqual(newest.source, "Изменение ШЕ")
        older = rows[1]
        self.assertEqual(older.start_at, "01.09.2026 08:30")
        self.assertEqual(older.end_at, "05.09.2026 17:15")
        self.assertEqual(older.source, "Назначение")

    def test_baseline_label_has_no_obsolete_version_number(self):
        self.assertEqual(SOURCE_LABELS["baseline"], "Начальное состояние")

    def test_employee_filter_and_table(self):
        self.assertEqual(len(self.report.rows(self.employee_id)), 2)
        self.assertEqual(self.report.rows(self.employee_id + 1000), ())
        table = self.report.table(self.employee_id)
        self.assertEqual(table.headers, assignment_history_headers())
        self.assertEqual(len(table.rows), 2)
        self.assertTrue(all(len(row) == 10 for row in table.rows))

    def test_csv_filename_is_stable(self):
        self.assertEqual(
            default_assignment_history_csv_name(date(2026, 9, 9)),
            "История_назначений_2026-09-09.csv",
        )


if __name__ == "__main__":
    unittest.main()
