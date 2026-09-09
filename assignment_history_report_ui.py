"""UI for the assignment history report."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from assignment_history import AssignmentHistoryService
from assignment_history_report import (
    AssignmentHistoryReport,
    assignment_history_headers,
    default_assignment_history_csv_name,
)
from reports import ReportExportError, render_tsv, write_csv


def install_assignment_history_report_ui(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QComboBox,
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

    if getattr(window, "_assignment_history_report_ui_installed", False):
        return
    reports_box = window.findChild(QGroupBox, "reportsGroup")
    if reports_box is None or reports_box.layout() is None:
        return

    history = getattr(window, "assignment_history", None) or AssignmentHistoryService(window.db)
    report_service = AssignmentHistoryReport(history)

    class AssignmentHistoryReportView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("assignmentHistoryReportView")
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(10)

            title = QLabel("История назначений")
            title.setObjectName("pageTitle")
            root.addWidget(title)

            controls = QHBoxLayout()
            self.employee = QComboBox()
            self.employee.addItem("Все работники", None)
            for person in window.service.list_employees(include_archived=True):
                self.employee.addItem(
                    f"{person['fio']} ({person['personnel_no']})", int(person["id"])
                )
            refresh_button = QPushButton("Обновить")
            refresh_button.setProperty("role", "primary")
            controls.addWidget(QLabel("Работник:"))
            controls.addWidget(self.employee, 1)
            controls.addWidget(refresh_button)
            root.addLayout(controls)

            hint = QLabel(
                "История ведётся с момента включения учёта v0.8. "
                "Более ранние назначения приложение не восстанавливает задним числом."
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

            headers = list(assignment_history_headers())
            self.table = QTableWidget(0, len(headers))
            self.table.setObjectName("assignmentHistoryReportTable")
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().hide()
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            root.addWidget(self.table, 1)

            self.empty_state = QLabel("История назначений пуста")
            self.empty_state.setObjectName("secondaryText")
            self.empty_state.setAlignment(Qt.AlignCenter)
            self.empty_state.hide()
            root.addWidget(self.empty_state, 1)

            refresh_button.clicked.connect(self.refresh)
            self.employee.currentIndexChanged.connect(self.refresh)
            copy_button.clicked.connect(self.copy_report)
            export_button.clicked.connect(self.export_csv)
            self.refresh_button = refresh_button
            self.copy_button = copy_button
            self.export_button = export_button
            self.refresh()

        def _table_data(self):
            return report_service.table(self.employee.currentData())

        def refresh(self) -> None:
            report = self._table_data()
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
                self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        def copy_report(self) -> None:
            report = self._table_data()
            QApplication.clipboard().setText(render_tsv(report.headers, report.rows))
            QMessageBox.information(self, "История назначений", "Отчёт скопирован в буфер обмена.")

        def export_csv(self, destination: str | Path | None = None) -> Path | None:
            report = self._table_data()
            target = destination
            if target is None:
                default = Path(window.db.path).parent / default_assignment_history_csv_name()
                filename, _ = QFileDialog.getSaveFileName(
                    self, "Экспорт отчёта «История назначений»", str(default), "CSV (*.csv)"
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

    class AssignmentHistoryReportDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Отчёты — История назначений")
            self.resize(1240, 700)
            root = QVBoxLayout(self)
            self.view = AssignmentHistoryReportView(self)
            root.addWidget(self.view, 1)
            close = QPushButton("Закрыть")
            close.clicked.connect(self.accept)
            bottom = QHBoxLayout()
            bottom.addStretch()
            bottom.addWidget(close)
            root.addLayout(bottom)

    def open_report() -> None:
        AssignmentHistoryReportDialog(window).exec()

    row = QHBoxLayout()
    button = QPushButton("История назначений")
    button.setProperty("role", "primary")
    button.clicked.connect(open_report)
    row.addWidget(button)
    row.addStretch()
    reports_box.layout().addLayout(row)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addAction("Отчёт: история назначений", open_report)

    window.assignment_history_report_view_type = AssignmentHistoryReportView
    window.assignment_history_report_dialog_type = AssignmentHistoryReportDialog
    window.open_assignment_history_report = open_report
    window._assignment_history_report_ui_installed = True
