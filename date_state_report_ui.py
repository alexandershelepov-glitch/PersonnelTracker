"""UI entry point for the v0.9.1 personnel state-on-date report."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from date_state_report import (
    PersonnelDateStateReport,
    date_state_headers,
    default_date_state_csv_name,
)
from reports import ReportExportError, render_tsv, write_csv


def install_date_state_report_ui(window: Any) -> None:
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QComboBox,
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

    if getattr(window, "_date_state_report_ui_installed", False):
        return

    temporal = getattr(window, "temporal_personnel", None)
    reports_box = window.findChild(QGroupBox, "reportsGroup")
    if temporal is None or reports_box is None or reports_box.layout() is None:
        return

    report_service = PersonnelDateStateReport(temporal)

    class DateStateView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("dateStateReportView")
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(10)

            title = QLabel("Состояние личного состава на дату")
            title.setObjectName("pageTitle")
            root.addWidget(title)

            controls = QHBoxLayout()
            self.when = QDateEdit(calendarPopup=True)
            self.when.setDisplayFormat("dd.MM.yyyy")
            self.when.setMinimumDate(
                QDate.fromString(temporal.history.tracking_started_date.isoformat(), "yyyy-MM-dd")
            )
            self.when.setMaximumDate(QDate.currentDate())
            self.when.setDate(QDate.currentDate())
            self.filter = QComboBox()
            self.filter.addItem("Все", False)
            self.filter.addItem("Недоступные", True)
            refresh_button = QPushButton("Обновить")
            refresh_button.setProperty("role", "primary")
            controls.addWidget(QLabel("Дата:"))
            controls.addWidget(self.when)
            controls.addWidget(QLabel("Показать:"))
            controls.addWidget(self.filter)
            controls.addWidget(refresh_button)
            controls.addStretch()
            root.addLayout(controls)

            self.summary_label = QLabel()
            self.summary_label.setWordWrap(True)
            root.addWidget(self.summary_label)

            hint = QLabel(
                "Источник — исторический срез v0.8.2. «Недоступные» — это существующее "
                "состояние доступности сервиса, поэтому сюда входят и выходные по графику."
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

            headers = list(date_state_headers())
            self.table = QTableWidget(0, len(headers))
            self.table.setObjectName("dateStateReportTable")
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().hide()
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.Stretch)
            root.addWidget(self.table, 1)

            self.empty_state = QLabel("На выбранную дату нет строк для отображения")
            self.empty_state.setObjectName("secondaryText")
            self.empty_state.setAlignment(Qt.AlignCenter)
            self.empty_state.hide()
            root.addWidget(self.empty_state, 1)

            refresh_button.clicked.connect(self.refresh)
            self.when.dateChanged.connect(self.refresh)
            self.filter.currentIndexChanged.connect(self.refresh)
            copy_button.clicked.connect(self.copy_report)
            export_button.clicked.connect(self.export_csv)
            self.refresh_button = refresh_button
            self.copy_button = copy_button
            self.export_button = export_button
            self.refresh()

        def target_date(self) -> str:
            return self.when.date().toString("yyyy-MM-dd")

        def unavailable_only(self) -> bool:
            return bool(self.filter.currentData())

        def _table_data(self):
            return report_service.table(self.target_date(), unavailable_only=self.unavailable_only())

        def refresh(self) -> None:
            try:
                data = self._table_data()
                summary = temporal.summary(self.target_date())
            except ValueError as exc:
                QMessageBox.warning(self, "Состояние на дату", str(exc))
                return

            self.summary_label.setText(
                f"Всего: {summary.total} · В ШДС: {summary.assigned} · Вне ШДС: {summary.unassigned} · "
                f"Доступны: {summary.available} · Недоступны: {summary.unavailable} · "
                f"Требуют проверки: {summary.needs_check}"
            )
            self.table.setRowCount(len(data.rows))
            for row_index, values in enumerate(data.rows):
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self.table.setItem(row_index, column, item)
            has_rows = bool(data.rows)
            self.table.setVisible(has_rows)
            self.empty_state.setVisible(not has_rows)
            self.copy_button.setEnabled(has_rows)
            self.export_button.setEnabled(has_rows)
            if has_rows:
                self.table.resizeColumnsToContents()
                self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        def copy_report(self) -> None:
            try:
                data = self._table_data()
            except ValueError as exc:
                QMessageBox.warning(self, "Состояние на дату", str(exc))
                return
            QApplication.clipboard().setText(render_tsv(data.headers, data.rows))
            QMessageBox.information(self, "Отчёты", "Отчёт скопирован в буфер обмена.")

        def export_csv(self, destination: str | Path | None = None) -> Path | None:
            try:
                data = self._table_data()
            except ValueError as exc:
                QMessageBox.warning(self, "Состояние на дату", str(exc))
                return None
            target = destination
            if target is None:
                default = Path(window.db.path).parent / default_date_state_csv_name(
                    self.target_date(), unavailable_only=self.unavailable_only()
                )
                filename, _ = QFileDialog.getSaveFileName(
                    self,
                    "Экспорт отчёта «Состояние личного состава на дату»",
                    str(default),
                    "CSV (*.csv)",
                )
                if not filename:
                    return None
                target = filename
            try:
                path = write_csv(target, data.headers, data.rows)
            except ReportExportError as exc:
                QMessageBox.critical(self, "Экспорт CSV", str(exc))
                return None
            if destination is None:
                QMessageBox.information(self, "Экспорт CSV", f"CSV успешно сохранён:\n{path}")
            return path

    class DateStateDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Отчёты — Состояние личного состава на дату")
            self.resize(1320, 720)
            root = QVBoxLayout(self)
            self.view = DateStateView(self)
            root.addWidget(self.view, 1)
            close = QPushButton("Закрыть")
            close.clicked.connect(self.accept)
            bottom = QHBoxLayout()
            bottom.addStretch()
            bottom.addWidget(close)
            root.addLayout(bottom)

    def open_date_state() -> None:
        DateStateDialog(window).exec()

    actions = QHBoxLayout()
    open_button = QPushButton("Состояние на дату")
    open_button.setProperty("role", "primary")
    open_button.clicked.connect(open_date_state)
    actions.addWidget(open_button)
    actions.addStretch()
    reports_box.layout().addLayout(actions)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addAction("Отчёт: состояние на дату", open_date_state)

    window.date_state_report_view_type = DateStateView
    window.date_state_report_dialog_type = DateStateDialog
    window.open_date_state_report = open_date_state
    window._date_state_report_ui_installed = True
