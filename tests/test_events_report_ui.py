from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate, QSettings
from PySide6.QtWidgets import QApplication, QGroupBox, QMessageBox, QPushButton

from events_report import EventsReport, events_headers
from events_report_ui import install_events_report_ui
from reports import render_tsv
from reports_ui import install_reports_ui
from ui import MainWindow

EVENT_YEAR, EVENT_MONTH = 2026, 9


class EventsReportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        install_reports_ui(self.window)
        install_events_report_ui(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _add_employee(self, number: str, fio: str) -> int:
        return self.window.service.save_employee({
            "fio": fio,
            "personnel_no": number,
            "department": "3 отдел",
            "position": "инспектор",
            "section": "1 отделение",
            "group_name": "1 группа",
            "schedule_type": "1/3",
            "employment_status": "Работает",
        })

    def _fill_sample(self) -> None:
        emp1 = self._add_employee("101", "Иванов Иван Иванович")
        emp2 = self._add_employee("202", "Петров Пётр Петрович")
        emp3 = self._add_employee("303", "Сидоров Алексей Сергеевич")
        self.window.service.add_event({
            "employee_id": str(emp1),
            "event_type": "Сборы",
            "subtype": "",
            "start_date": f"{EVENT_YEAR}-09-10",
            "end_date": f"{EVENT_YEAR}-09-12",
            "location": "Полигон",
            "basis": "",
            "notes": "",
        })
        self.window.service.create_batch_events(
            [emp2, emp3],
            {
                "event_type": "Сдача медкомиссии",
                "subtype": "",
                "start_date": f"{EVENT_YEAR}-09-15",
                "end_date": f"{EVENT_YEAR}-09-15",
                "location": "",
                "basis": "",
                "notes": "",
            },
        )

    def _show_month(self, view, year: int, month: int, refresh: bool = True) -> None:
        first = QDate(year, month, 1)
        last = first.addMonths(1).addDays(-1)
        view.start.setDate(first)
        view.end.setDate(last)
        if refresh:
            view.refresh()
        self.app.processEvents()

    def test_install_is_idempotent_and_adds_single_button(self):
        install_events_report_ui(self.window)
        box = self.window.findChild(QGroupBox, "reportsGroup")
        buttons = [button.text() for button in box.findChildren(QPushButton)]
        self.assertEqual(buttons.count("События и привлечение"), 1)
        self.assertTrue(callable(self.window.open_events_report))

    def test_table_has_eleven_columns_matching_events_headers(self):
        view = self.window.events_report_view_type()
        self.assertEqual(view.table.columnCount(), 11)
        labels = [view.table.horizontalHeaderItem(index).text() for index in range(11)]
        self.assertEqual(labels, list(events_headers()))
        view.deleteLater()
        self.app.processEvents()

    def test_single_and_batch_events_are_displayed(self):
        self._fill_sample()
        view = self.window.events_report_view_type()
        self._show_month(view, EVENT_YEAR, EVENT_MONTH)
        self.assertEqual(view.table.rowCount(), 3)
        # column 7 = ФИО, 9 = Формат, 10 = Участников
        formats = [view.table.item(r, 9).text() for r in range(3)]
        self.assertEqual(formats.count("Одиночное"), 1)
        self.assertEqual(formats.count("Групповое"), 2)
        by_fio = {view.table.item(r, 7).text(): int(view.table.item(r, 10).text()) for r in range(3)}
        self.assertEqual(by_fio["Иванов Иван Иванович"], 1)
        self.assertEqual(by_fio["Петров Пётр Петрович"], 2)
        self.assertEqual(by_fio["Сидоров Алексей Сергеевич"], 2)
        view.deleteLater()
        self.app.processEvents()

    def test_changing_period_changes_rows_and_empty_state(self):
        self._fill_sample()
        view = self.window.events_report_view_type()
        view.show()
        self.app.processEvents()
        self._show_month(view, EVENT_YEAR, EVENT_MONTH)
        self.assertEqual(view.table.rowCount(), 3)
        self.assertFalse(view.empty_state.isVisible())

        self._show_month(view, 2026, 1)
        self.assertEqual(view.table.rowCount(), 0)
        self.assertTrue(view.empty_state.isVisible())
        self.assertFalse(view.table.isVisible())

        self._show_month(view, EVENT_YEAR, EVENT_MONTH)
        self.assertEqual(view.table.rowCount(), 3)
        view.deleteLater()
        self.app.processEvents()

    def test_refresh_does_not_duplicate_rows(self):
        self._fill_sample()
        view = self.window.events_report_view_type()
        self._show_month(view, EVENT_YEAR, EVENT_MONTH)
        self.assertEqual(view.table.rowCount(), 3)
        view.refresh()
        self.app.processEvents()
        self.assertEqual(view.table.rowCount(), 3)
        view.deleteLater()
        self.app.processEvents()

    def test_empty_selection_shows_empty_state(self):
        view = self.window.events_report_view_type()
        view.show()
        self.app.processEvents()
        self._show_month(view, 2026, 1)
        self.assertEqual(view.table.rowCount(), 0)
        self.assertTrue(view.empty_state.isVisible())
        self.assertFalse(view.table.isVisible())
        view.deleteLater()
        self.app.processEvents()

    def test_copy_uses_current_report_data(self):
        self._fill_sample()
        view = self.window.events_report_view_type()
        self._show_month(view, EVENT_YEAR, EVENT_MONTH)
        start, end = view._period()
        expected = EventsReport(self.window.service).table(start, end)
        with patch.object(QMessageBox, "information"):
            view.copy_report()
        self.assertEqual(
            QApplication.clipboard().text(),
            render_tsv(expected.headers, expected.rows),
        )
        view.deleteLater()
        self.app.processEvents()

    def test_export_csv_creates_file_without_dialog(self):
        self._fill_sample()
        view = self.window.events_report_view_type()
        self._show_month(view, EVENT_YEAR, EVENT_MONTH)
        destination = Path(self.tmp.name) / "out.csv"
        with patch.object(QMessageBox, "information") as info:
            result = view.export_csv(destination=destination)
        self.assertEqual(result, destination.resolve())
        self.assertTrue(destination.exists())
        content = destination.read_text(encoding="utf-8-sig")
        self.assertIn("ФИО", content)
        self.assertIn("Иванов Иван Иванович", content)
        self.assertIn("Групповое", content)
        info.assert_not_called()
        view.deleteLater()
        self.app.processEvents()

    def test_reversed_period_shows_warning_without_crashing(self):
        view = self.window.events_report_view_type()
        view.start.setDate(QDate(EVENT_YEAR, 9, 30))
        view.end.setDate(QDate(EVENT_YEAR, 9, 1))
        with patch.object(QMessageBox, "warning") as warn:
            view.refresh()
        warn.assert_called_once()
        self.app.processEvents()
        view.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
