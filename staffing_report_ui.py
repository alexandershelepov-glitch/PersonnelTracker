"""UI entry point for the v0.9.1 staffing placement report."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from reports import ReportExportError, render_tsv, write_csv
from staffing_report import (
    StaffingPlacementReport,
    default_staffing_csv_name,
    staffing_headers,
)


def install_staffing_report_ui(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
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

    if getattr(window, "_staffing_report_ui_installed", False):
        return

    reports_box = window.findChild(QGroupBox, "reportsGroup")
    if reports_box is None or reports_box.layout() is None:
        return

    class StaffingPlacementView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("staffingPlacementView")
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(10)

            title = QLabel("Штатная расстановка")
            title.setObjectName("pageTitle")
            root.addWidget(title)

            hint = QLabel(
                "Все штатные единицы: занятые и вакантные. Организационные поля "
                "берутся непосредственно из штатной структуры."
            )
            hint.setObjectName("secondaryText")
            hint.setWordWrap(True)
            root.addWidget(hint)

            actions = QHBoxLayout()
            refresh_button = QPushButton("Обновить")
            copy_button = QPushButton("Копировать")
            export_button = QPushButton("Экспорт CSV")
            export_button.setProperty("role", "primary")
            actions.addWidget(refresh_button)
            actions.addWidget(copy_button)
            actions.addWidget(export_button)
            actions.addStretch()
            root.addLayout(actions)

            headers = list(staffing_headers())
            self.table = QTableWidget(0, len(headers))
            self.table.setObjectName("staffingPlacementTable")
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().hide()
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.Stretch)
            header.setStretchLastSection(False)
            root.addWidget(self.table, 1)

            self.empty_state = QLabel("Штатные единицы не заведены")
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

        def _table_data(self):
            return StaffingPlacementReport(window.service).table()

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
                self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        def copy_report(self) -> None:
            report = self._table_data()
            QApplication.clipboard().setText(render_tsv(report.headers, report.rows))
            QMessageBox.information(self, "Отчёты", "Отчёт скопирован в буфер обмена.")

        def export_csv(self, destination: str | Path | None = None) -> Path | None:
            report = self._table_data()
            target = destination
            if target is None:
                default = Path(window.db.path).parent / default_staffing_csv_name(date.today())
                filename, _ = QFileDialog.getSaveFileName(
                    self,
                    "Экспорт отчёта «Штатная расстановка»",
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

    class StaffingPlacementDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Отчёты — Штатная расстановка")
            self.resize(1220, 680)
            root = QVBoxLayout(self)
            self.view = StaffingPlacementView(self)
            root.addWidget(self.view, 1)
            close = QPushButton("Закрыть")
            close.clicked.connect(self.accept)
            bottom = QHBoxLayout()
            bottom.addStretch()
            bottom.addWidget(close)
            root.addLayout(bottom)

        def refresh(self) -> None:
            self.view.refresh()

    def open_staffing() -> None:
        StaffingPlacementDialog(window).exec()

    actions = QHBoxLayout()
    open_button = QPushButton("Штатная расстановка")
    open_button.setProperty("role", "primary")
    open_button.clicked.connect(open_staffing)
    actions.addWidget(open_button)
    actions.addStretch()
    reports_box.layout().addLayout(actions)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addAction("Отчёт: штатная расстановка", open_staffing)

    window.staffing_placement_view_type = StaffingPlacementView
    window.staffing_placement_dialog_type = StaffingPlacementDialog
    window.open_staffing_placement_report = open_staffing
    window._staffing_report_ui_installed = True
