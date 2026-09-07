"""Reports workspace for PersonnelTracker v0.9.1.

Starts a dedicated «Отчёты» section without adding a fifth sidebar workflow.
The first report is the active-personnel roster.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from reports import (
    PersonnelRosterReport,
    ReportExportError,
    default_roster_csv_name,
    render_tsv,
    roster_headers,
    write_csv,
)


def install_reports_ui(window: Any) -> None:
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

    if getattr(window, "_reports_ui_installed", False):
        return

    class PersonnelRosterView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("personnelRosterView")
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(10)

            title = QLabel("Личный состав")
            title.setObjectName("pageTitle")
            root.addWidget(title)

            hint = QLabel(
                "Действующие работники. Подразделение, отделение, группа и должность "
                "берутся из штатного назначения, если оно есть."
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

            headers = list(roster_headers())
            self.table = QTableWidget(0, len(headers))
            self.table.setObjectName("personnelRosterTable")
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().hide()
            header = self.table.horizontalHeader()
            header.setStretchLastSection(True)
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            root.addWidget(self.table, 1)

            self.empty_state = QLabel("Действующих работников нет")
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
            return PersonnelRosterReport(window.service).table()

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

        def copy_report(self) -> None:
            report = self._table_data()
            QApplication.clipboard().setText(render_tsv(report.headers, report.rows))
            QMessageBox.information(self, "Отчёты", "Отчёт скопирован в буфер обмена.")

        def export_csv(self, destination: str | Path | None = None) -> Path | None:
            report = self._table_data()
            target = destination
            if target is None:
                default = Path(window.db.path).parent / default_roster_csv_name(date.today())
                filename, _ = QFileDialog.getSaveFileName(
                    self,
                    "Экспорт отчёта «Личный состав»",
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

    class PersonnelRosterDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Отчёты")
            self.resize(1180, 640)
            root = QVBoxLayout(self)
            self.view = PersonnelRosterView(self)
            root.addWidget(self.view, 1)
            close = QPushButton("Закрыть")
            close.clicked.connect(self.accept)
            bottom = QHBoxLayout()
            bottom.addStretch()
            bottom.addWidget(close)
            root.addLayout(bottom)

        def refresh(self) -> None:
            self.view.refresh()

    def open_roster() -> None:
        PersonnelRosterDialog(window).exec()

    def settings_layout():
        layout = getattr(window, "service_scroll_layout", None)
        if layout is not None:
            return layout
        page = window.pages.widget(4)
        return page.layout() if page is not None else None

    layout = settings_layout()
    if layout is None:
        return

    box = QGroupBox("Отчёты")
    box.setObjectName("reportsGroup")
    box_layout = QVBoxLayout(box)
    description = QLabel(
        "Рабочие выгрузки на основе уже существующих данных приложения. "
        "Первый отчёт — действующий личный состав."
    )
    description.setWordWrap(True)
    box_layout.addWidget(description)
    actions = QHBoxLayout()
    open_button = QPushButton("Личный состав")
    open_button.setProperty("role", "primary")
    open_button.clicked.connect(open_roster)
    actions.addWidget(open_button)
    actions.addStretch()
    box_layout.addLayout(actions)
    layout.insertWidget(max(0, layout.count() - 1), box)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addSeparator()
        service_menu.addAction("Отчёт: личный состав", open_roster)

    window.personnel_roster_view_type = PersonnelRosterView
    window.personnel_roster_dialog_type = PersonnelRosterDialog
    window.open_personnel_roster_report = open_roster
    window._reports_ui_installed = True
