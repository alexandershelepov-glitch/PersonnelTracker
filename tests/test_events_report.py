from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database
from events_report import (
    EMPTY_VALUE,
    GROUP_LABEL,
    SINGLE_LABEL,
    PERIOD_ERROR,
    EventsReport,
    events_headers,
)
from services import PersonnelService

PERIOD_START = "2026-09-01"
PERIOD_END = "2026-09-30"


def _employee_data(number: str, fio: str) -> dict:
    return {
        "fio": fio,
        "personnel_no": number,
        "department": "3 отдел",
        "position": "инспектор",
        "section": "1 отделение",
        "group_name": "1 группа",
        "schedule_type": "1/3",
        "employment_status": "Работает",
    }


def _event_data(**overrides) -> dict:
    data: dict = {
        "event_type": "Сборы",
        "subtype": "",
        "start_date": "2026-09-10",
        "end_date": "2026-09-12",
        "location": "Полигон",
        "basis": "",
        "notes": "",
    }
    data.update(overrides)
    return data


class EventsReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        self.service = PersonnelService(self.db)
        self.report = EventsReport(self.service)
        self.emp1 = self.service.save_employee(_employee_data("101", "Иванов Иван Иванович"))
        self.emp2 = self.service.save_employee(_employee_data("202", "Петров Пётр Петрович"))
        self.emp3 = self.service.save_employee(_employee_data("303", "Сидоров Алексей Сергеевич"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_stable_header_order(self):
        self.assertEqual(events_headers(), (
            "С", "По", "Тип события", "Подтип", "Место / объект",
            "Основание", "Примечание", "ФИО", "Табельный номер",
            "Формат", "Участников",
        ))

    def test_single_event_is_одиночное_with_one_participant(self):
        self.service.add_event({**_event_data(), "employee_id": str(self.emp1)})
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].format, SINGLE_LABEL)
        self.assertEqual(rows[0].participants, "1")
        self.assertEqual(rows[0].fio, "Иванов Иван Иванович")

    def test_batch_rows_are_групповое_and_count_members(self):
        self.service.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row.format, GROUP_LABEL)
            self.assertEqual(row.participants, "3")
        self.assertEqual({row.fio for row in rows},
                         {"Иванов Иван Иванович", "Петров Пётр Петрович", "Сидоров Алексей Сергеевич"})

    def test_one_row_per_batch_worker(self):
        self.service.create_batch_events([self.emp1, self.emp2], _event_data())
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row.format for row in rows], [GROUP_LABEL, GROUP_LABEL])

    def test_single_and_batch_participant_counts_do_not_interfere(self):
        self.service.add_event({**_event_data(), "employee_id": str(self.emp1)})
        self.service.create_batch_events([self.emp2, self.emp3], _event_data())
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        by_fio = {row.fio: row for row in rows}
        self.assertEqual(len(rows), 3)
        self.assertEqual(by_fio["Иванов Иван Иванович"].format, SINGLE_LABEL)
        self.assertEqual(by_fio["Иванов Иван Иванович"].participants, "1")
        self.assertEqual(by_fio["Петров Пётр Петрович"].participants, "2")
        self.assertEqual(by_fio["Сидоров Алексей Сергеевич"].participants, "2")

    def test_event_overlapping_period_is_included(self):
        # Event begins before period start and ends inside the period.
        self.service.add_event({**_event_data(start_date="2026-08-25", end_date="2026-09-05"),
                                "employee_id": str(self.emp1)})
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].start_date, "25.08.2026")
        self.assertEqual(rows[0].end_date, "05.09.2026")

    def test_inclusion_on_boundary_dates(self):
        # Single-day event exactly on period start and on period end.
        self.service.add_event({**_event_data(start_date="2026-09-01", end_date="2026-09-01"),
                                "employee_id": str(self.emp1)})
        self.service.add_event({**_event_data(start_date="2026-09-30", end_date="2026-09-30"),
                                "employee_id": str(self.emp2)})
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        self.assertEqual(len(rows), 2)

    def test_event_touching_boundary_is_included(self):
        # Event ends exactly on period start and another starts on period end.
        self.service.add_event({**_event_data(start_date="2026-08-20", end_date="2026-09-01"),
                                "employee_id": str(self.emp1)})
        self.service.add_event({**_event_data(start_date="2026-09-30", end_date="2026-10-05"),
                                "employee_id": str(self.emp2)})
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        self.assertEqual(len(rows), 2)

    def test_event_outside_period_is_excluded(self):
        self.service.add_event({**_event_data(start_date="2026-07-01", end_date="2026-07-05"),
                                "employee_id": str(self.emp1)})
        self.service.add_event({**_event_data(start_date="2026-10-01", end_date="2026-10-05"),
                                "employee_id": str(self.emp2)})
        rows = self.report.rows(PERIOD_START, PERIOD_END)
        self.assertEqual(rows, ())

    def test_reversed_period_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "периода"):
            self.report.rows("2026-09-30", "2026-09-01")
        with self.assertRaises(ValueError) as ctx:
            self.report.table("2026-09-30", "2026-09-01")
        self.assertEqual(str(ctx.exception), PERIOD_ERROR)

    def test_empty_subtype_location_basis_notes_use_placeholder(self):
        self.service.add_event({**_event_data(subtype="", location="", basis="", notes=""),
                                "employee_id": str(self.emp1)})
        row = self.report.rows(PERIOD_START, PERIOD_END)[0]
        self.assertEqual(row.subtype, EMPTY_VALUE)
        self.assertEqual(row.location, EMPTY_VALUE)
        self.assertEqual(row.basis, EMPTY_VALUE)
        self.assertEqual(row.notes, EMPTY_VALUE)

    def test_filled_text_fields_are_kept(self):
        self.service.add_event({
            **_event_data(subtype="учебные", location="Полигон", basis="Приказ №1", notes="Обязательно"),
            "employee_id": str(self.emp1),
        })
        row = self.report.rows(PERIOD_START, PERIOD_END)[0]
        self.assertEqual(row.subtype, "учебные")
        self.assertEqual(row.location, "Полигон")
        self.assertEqual(row.basis, "Приказ №1")
        self.assertEqual(row.notes, "Обязательно")

    def test_dates_in_russian_format(self):
        self.service.add_event({**_event_data(start_date="2026-09-05", end_date="2026-09-07"),
                                "employee_id": str(self.emp1)})
        row = self.report.rows(PERIOD_START, PERIOD_END)[0]
        self.assertEqual(row.start_date, "05.09.2026")
        self.assertEqual(row.end_date, "07.09.2026")

    def test_empty_database_returns_no_rows(self):
        self.assertEqual(self.report.rows(PERIOD_START, PERIOD_END), ())

    def test_table_rows_match_headers_count(self):
        self.service.create_batch_events([self.emp1, self.emp2, self.emp3], _event_data())
        table = self.report.table(PERIOD_START, PERIOD_END)
        self.assertEqual(table.headers, events_headers())
        self.assertEqual(len(table.headers), 11)
        self.assertEqual(len(table.rows), 3)
        for values in table.rows:
            self.assertEqual(len(values), 11)


if __name__ == "__main__":
    unittest.main()
