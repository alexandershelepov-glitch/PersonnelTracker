from __future__ import annotations

import sqlite3
import json
from datetime import date
from pathlib import Path
from collections import defaultdict

from PySide6.QtCore import QDate, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPixmap, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QCompleter, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QStackedWidget, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QMenu, QScrollArea, QToolButton,
)

from config import APP_NAME, EVENT_TYPES, SCHEDULE_TYPES, SECTIONS
from database import Database
from services import BatchConflictError, PersonnelService, calculate_age, format_age, natural_sort_key
from theme import ThemeManager


NULL_DATE = QDate(1900, 1, 1)


def format_date(value: str | None) -> str:
    if not value:
        return "Не указано"
    parsed = QDate.fromString(value, "yyyy-MM-dd")
    return parsed.toString("dd.MM.yyyy") if parsed.isValid() else value


def new_date_edit(nullable: bool = False) -> QDateEdit:
    edit = QDateEdit(calendarPopup=True)
    edit.setDisplayFormat("dd.MM.yyyy")
    if nullable:
        edit.setMinimumDate(NULL_DATE)
        edit.setSpecialValueText("Не указано")
        edit.setDate(NULL_DATE)
    else:
        edit.setDate(QDate.currentDate())
    return edit


def iso_from_dateedit(widget: QDateEdit, nullable: bool = False) -> str | None:
    if nullable and widget.date() == NULL_DATE:
        return None
    return widget.date().toString("yyyy-MM-dd")


def set_dateedit(widget: QDateEdit, value: str | None, nullable: bool = False) -> None:
    parsed = QDate.fromString(value or "", "yyyy-MM-dd")
    widget.setDate(parsed if parsed.isValid() else (NULL_DATE if nullable else QDate.currentDate()))


def russian_dialog_buttons(save_text: str = "Сохранить") -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Save).setText(save_text)
    buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
    return buttons


def attach_completer(widget: QLineEdit, values: list[str]) -> None:
    completer = QCompleter(values)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    widget.setCompleter(completer)


def style_table(table: QTableWidget) -> None:
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setDefaultSectionSize(30)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)


def fit_to_available_screen(widget: QWidget, preferred_width: int, preferred_height: int,
                            minimum_width: int, minimum_height: int) -> None:
    """Choose a sensible initial size without exceeding the usable desktop area."""
    screen = widget.screen() or QApplication.primaryScreen()
    if screen is None:
        widget.resize(preferred_width, preferred_height)
        return
    area = screen.availableGeometry()
    width = min(preferred_width, max(minimum_width, int(area.width() * 0.88)))
    height = min(preferred_height, max(minimum_height, int(area.height() * 0.88)))
    widget.resize(min(width, area.width()), min(height, area.height()))


class SpreadsheetTable(QTableWidget):
    """Read-only table with spreadsheet-compatible copying of visible cells."""
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            rows = sorted({index.row() for index in self.selectedIndexes()})
            columns = [column for column in range(self.columnCount()) if not self.isColumnHidden(column)]
            text = "\n".join("\t".join((self.item(row, column).text() if self.item(row, column) else "") for column in columns) for row in rows)
            QApplication.clipboard().setText(text)
            event.accept()
            return
        super().keyPressEvent(event)


class PhotoLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class EmployeeDialog(QDialog):
    def __init__(self, service: PersonnelService, employee_id: int | None = None, parent=None):
        super().__init__(parent)
        self.service, self.employee_id = service, employee_id
        self.created_in_dialog = False
        self.current_daily_status: str | None = None
        self.setWindowTitle("Карточка работника")
        self.setMinimumSize(640, 480)
        fit_to_available_screen(self, 1040, 720, 640, 480)
        self.tabs = QTabWidget(); self.main_tab = QWidget()
        self.main_scroll = QScrollArea(); self.main_scroll.setWidgetResizable(True); self.main_scroll.setWidget(self.main_tab)
        self.tabs.addTab(self.main_scroll, "Основное")
        self._build_main(); self._build_record_tabs()
        self._clean_state = self.form_state()
        buttons = russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.button(QDialogButtonBox.Cancel).hide()
        close = QPushButton("Закрыть"); close.clicked.connect(self.close)
        root = QVBoxLayout(self); root.addWidget(self.tabs); bottom = QHBoxLayout(); bottom.addStretch(); bottom.addWidget(close); bottom.addWidget(buttons); root.addLayout(bottom)
        if employee_id:
            self.load_employee(); self.refresh_records()

    def _build_main(self) -> None:
        root = QVBoxLayout(self.main_tab)
        card = QGroupBox("Карточка работника")
        card_layout = QGridLayout(card)
        self.photo = PhotoLabel("ФОТО"); self.photo.setObjectName("photoFrame"); self.photo.setFixedSize(140, 175); self.photo.setAlignment(Qt.AlignCenter)
        self.photo.setToolTip("Щёлкните, чтобы открыть фотографию")
        self.photo.clicked.connect(self.show_photo)
        card_layout.addWidget(self.photo, 0, 0, 5, 1)
        self.header_fio = QLabel("Новый работник"); self.header_fio.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.header_position = QLabel("Должность: не указано"); self.header_department = QLabel("Подразделение: не указано"); self.header_section = QLabel("Отделение: не указано")
        self.header_meta = QLabel("Табельный №: не указан    •    Статус на сегодня: —")
        card_layout.addWidget(self.header_fio, 0, 1); card_layout.addWidget(self.header_position, 1, 1); card_layout.addWidget(self.header_department, 2, 1); card_layout.addWidget(self.header_section, 3, 1); card_layout.addWidget(self.header_meta, 4, 1)
        photo_actions = QVBoxLayout(); self.photo_add = QPushButton("Добавить фото"); self.photo_remove = QPushButton("Удалить фото"); self.photo_add.clicked.connect(self.choose_photo); self.photo_remove.clicked.connect(self.delete_photo); photo_actions.addWidget(self.photo_add); photo_actions.addWidget(self.photo_remove); photo_actions.addStretch(); card_layout.addLayout(photo_actions, 0, 2, 5, 1)
        self.copy_data=QComboBox(); self.copy_data.addItems(["Скопировать ▼","ФИО","ФИО + табельный номер","Телефон","Должность"]); self.copy_data.activated.connect(self.copy_employee_data); card_layout.addWidget(self.copy_data,4,2)
        root.addWidget(card)

        self.fio, self.personnel_no = QLineEdit(), QLineEdit(); self.fio.setMinimumWidth(420)
        self.department, self.position = QLineEdit(), QLineEdit(); self.section = QComboBox(); self.section.setEditable(True); self.section.setInsertPolicy(QComboBox.NoInsert); self.section.addItems(SECTIONS)
        self.birth_date, self.employment_date, self.archive_date = new_date_edit(True), new_date_edit(True), new_date_edit(True)
        self.factual_address, self.registration_address = QLineEdit(), QLineEdit()
        self.phone, self.email = QLineEdit(), QLineEdit()
        self.schedule_type = QComboBox(); self.schedule_type.addItems(SCHEDULE_TYPES)
        self.schedule_anchor = new_date_edit(True)
        self.schedule_anchor.setToolTip("Укажите любую известную рабочую смену. Остальные даты программа рассчитает автоматически.")
        self.employment_status = QComboBox(); self.employment_status.addItems(["Работает", "Уволен", "Переведён", "Архив"])
        self.latest_medical, self.latest_periodic = QLabel("Не указано"), QLabel("Не указано")
        self.fio.textChanged.connect(self.update_header); self.department.textChanged.connect(self.update_header); self.position.textChanged.connect(self.update_header); self.personnel_no.textChanged.connect(self.update_header); self.section.currentTextChanged.connect(self.update_header)
        self.employment_status.currentTextChang