"""UI entry point for the events & involvement report.

One dialog shows every existing event over a selected period.  It reuses the
read-only ``EventsReport`` data layer and does not classify event types,
filter vacations/sick leaves or add organisation data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from events_report import EventsReport, events_headers
from reports import ReportExportError, render_tsv, write_csv


def default_events_csv_name(year: int, month: int) -> str:
    return f"События_и_привлечение_{year:04d}-{month:02d}.csv"


def install_events_report_ui(window: Any) -> None:
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QDateEdit,
        QDialog,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    if getattr(window, "_events_report_ui_installed", False):
        return

    reports_box = window.findChild(QGroupBox, "reportsGroup")
    if reports_box is None or reports_box.layout() is None:
        return

    class EventsReportView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("eventsReportView")
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(10)

            title = QLabel("События и привлечение")
            title.setObjectName("pageTitle")
            root.addWidget(title)

            controls = QHBoxLayout()
            today = QDate.currentDate()
            month_start = QDate(today.year(), today.month(), 1)
            month_end = month_start.addMonths(1).addDays(-1)

            self.start = QDateEdit(calendarPopup=True)
            self.start.setDisplayFormat("dd.MM.yyyy")
            self.start.setDate(month_start)
            self.end = QDateEdit(calendarPopup=True)
            self.end.setDisplayFormat("dd.MM.yyyy")
            self.end.setDate(month_end)
            refresh_button = QPushButton("Обновить")
            refresh_button.setProperty("role", "primary")
            controls.addWidget(QLabel("С:"))
            controls.addWidget(self.start)
            controls.addWidget(QLabel("По:"))
            controls.addWidget(self.end)
            controls.addWidget(refresh_button)
            controls.addStretch()
            root.addLayout(controls)

            hint = QLabel(
                "Зарегистрированные события за период. Отпуска, больничные и другие "
                "события показываются как есть, без разделения на виды."
            )
            hint.setObjectName("secondaryText")
            hint.setWordWrap(True)
            root.addWidget(hint)

            actions = QHBoxLayout()
            copy_button = QPushButton("Копировать")
            export_button = QPushButton("Экспорт CSV")
            actions.addWidget(copy_button)
            actions.addWidget(export_button)
            actions.addStretch()
            root.addLayout(actions)

            headers = list(events_headers())
            self.table = QTableWidget(0, len(headers))
            self.table.setObjectName("eventsReportTable")
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().hide()
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setSectionResizeMode(7, QHeaderView.Stretch)
            header.setStretchLastSection(False)
            root.addWidget(self.table, 1)

            self.empty_state = QLabel("За выбранный период нет событий")
            self.empty_state.setObjectName("secondaryText")
            self.empty_state.setAlignment(Qt.AlignCenter)
            self.empty_state.hide()
            root.addWidget(self.empty_state, 1)

            refresh_button.clicked.connect(self.refresh)
            copy_button.clicked.connect(self.copy_report)
            export_button.clicked.connect(self.export_csv)
            self.refresh_button = refresh_button
            self.copy_button = copy_button
            self.export_button = export_button
            self.refresh()

        def _period(self) -> tuple[str, str]:
            return (
                self.start.date().toString("yyyy-MM-dd"),
                self.end.date().toString("yyyy-MM-dd"),
            )

        def _table_data(self):
            start_date, end_date = self._period()
            return EventsReport(window.service).table(start_date, end_date)

        def refresh(self) -> None:
            try:
                report = self._table_data()
            except ValueError as exc:
                QMessageBox.warning(self, "События и привлечение", str(exc))
                return
            self.table.setRowCount(len(report.rows))
            for row_index, values in enumerate(report.rows):
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self.table.setItem(row_index, column, item)
            has_rows = bool(report.rows)
            self.table.setVisible(has_rows)
            self.empty_state.setVisible(not has_rows)
            self.copy_button.setEnabled(has_rows)
            self.export_button.setEnabled(has_rows)
            if has_rows:
                self.table.resizeColumnsToContents()
                self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)

        def copy_report(self) -> None:
            report = self._table_data()
            QApplication.clipboard().setText(render_tsv(report.headers, report.rows))
            QMessageBox.information(self, "События и привлечение", "Отчёт скопирован в буфер обмена.")

        def export_csv(self, destination: str | Path | None = None) -> Path | None:
            report = self._table_data()
            target = destination
            if target is None:
                chosen = self.start.date()
                default = Path(window.db.path).parent / default_events_csv_name(chosen.year(), chosen.month())
                filename, _ = QFileDialog.getSaveFileName(
                    self,
                    "Экспорт отчёта «События и привлечение»",
                    str(default),
                    "CSV (*.csv)",
                )
                if not filename:
                    return None
                target = filename
            try:
                path = write_csv(target, report.headers, report.rows)
            except ReportExportError as exc:
                QMessageBox.critical(self, "Экспорт CSV", str(exc))
                return None
            if destination is None:
                QMessageBox.information(self, "Экспорт CSV", f"CSV успешно сохранён:\n{path}")
            return path

    class EventsReportDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Отчёты — События и привлечение")
            self.resize(1280, 700)
            root = QVBoxLayout(self)
            self.view = EventsReportView(self)
            root.addWidget(self.view, 1)
            close = QPushButton("Закрыть")
            close.clicked.connect(self.accept)
            bottom = QHBoxLayout()
            bottom.addStretch()
            bottom.addWidget(close)
            root.addLayout(bottom)

    def open_events() -> None:
        EventsReportDialog(window).exec()

    actions = QHBoxLayout()
    open_button = QPushButton("События и привлечение")
    open_button.setProperty("role", "primary")
    open_button.clicked.connect(open_events)
    actions.addWidget(open_button)
    actions.addStretch()
    reports_box.layout().addLayout(actions)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addAction("Отчёт: события и привлечение", open_events)

    window.events_report_view_type = EventsReportView
    window.events_report_dialog_type = EventsReportDialog
    window.open_events_report = open_events
    window._events_report_ui_installed = True
