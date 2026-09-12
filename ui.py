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
        fit_to_available_screen(self, 1120, 740, 640, 480)
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

        self.fio, self.personnel_no = QLineEdit(), QLineEdit(); self.fio.setMinimumWidth(340)
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
        self.employment_status.currentTextChanged.connect(self.update_header); self.employment_status.currentTextChanged.connect(self._status_changed)
        self.birth_date.dateChanged.connect(self.update_age)
        forms = QGridLayout(); forms.setColumnStretch(0, 1); forms.setColumnStretch(1, 1)
        self.education = QComboBox(); self.education.setEditable(True); self.education.setInsertPolicy(QComboBox.NoInsert); self.education.addItems(["", "высшее", "среднее профессиональное", "среднее общее"]); attach_completer(self.education.lineEdit(), ["высшее", "среднее профессиональное", "среднее общее"])
        self.age_label=QLabel("Не указан"); personal = QGroupBox("Личные данные"); f = QFormLayout(personal); f.addRow("ФИО*", self.fio); f.addRow("Табельный номер*", self.personnel_no); f.addRow("Дата рождения", self.birth_date); f.addRow("Возраст", self.age_label); f.addRow("Дата начала работы", self.employment_date); f.addRow("Образование", self.education)
        contacts = QGroupBox("Контакты"); f = QFormLayout(contacts); f.addRow("Телефон", self.phone); f.addRow("E-mail", self.email)
        addresses = QGroupBox("Адреса"); f = QFormLayout(addresses); f.addRow("Фактический адрес", self.factual_address); f.addRow("Адрес регистрации", self.registration_address)
        self.group_label = QLineEdit(); self.group_label.setPlaceholderText("Например, 1 группа")
        self.assignment_status = QLabel("Не назначен на штатную единицу"); self.assignment_status.setWordWrap(True)
        self.certificate_number = QLineEdit()
        service = QGroupBox("Служебные данные"); f = QFormLayout(service); f.setRowWrapPolicy(QFormLayout.WrapLongRows); f.addRow("Подразделение", self.department); f.addRow("Отделение", self.section); f.addRow("Группа", self.group_label); f.addRow("Должность", self.position); f.addRow("Номер удостоверения", self.certificate_number); f.addRow("Статус работника", self.employment_status); f.addRow("С какого числа отсутствует", self.archive_date); f.addRow("Штатное назначение", self.assignment_status)
        self._apply_field_completers()
        schedule = QGroupBox("График работы"); f = QFormLayout(schedule); f.addRow("График", self.schedule_type); f.addRow("Дата рабочей смены", self.schedule_anchor)
        schedule_hint = QLabel("Укажите любую известную рабочую смену. Остальные даты программа рассчитает автоматически."); schedule_hint.setWordWrap(True); schedule_hint.setObjectName("secondaryText"); f.addRow(schedule_hint)
        control = QGroupBox("Контроль"); f = QFormLayout(control); f.addRow("Последняя медкомиссия", self._summary_row(self.latest_medical, "Медкомиссия")); f.addRow("Последняя периодическая проверка", self._summary_row(self.latest_periodic, "Периодическая проверка"))
        forms.addWidget(personal, 0, 0); forms.addWidget(service, 0, 1); forms.addWidget(contacts, 1, 0); forms.addWidget(addresses, 1, 1); forms.addWidget(schedule, 2, 0); forms.addWidget(control, 2, 1)
        root.addLayout(forms); root.addStretch()

    def _summary_row(self, label: QLabel, tab_name: str) -> QWidget:
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(label); button = QPushButton("Открыть журнал"); button.clicked.connect(lambda: self.open_record_tab(tab_name)); layout.addWidget(button); layout.addStretch(); return row

    def _build_record_tabs(self) -> None:
        self.record_tables: dict[str, QTableWidget] = {}
        sections = [
            ("Медкомиссия", ["Дата", "Примечание"], self.add_medical, self.edit_medical, self.delete_medical),
            ("Периодическая проверка", ["Дата", "Результат", "Примечание"], self.add_periodic, self.edit_periodic, self.delete_periodic),
            ("Обучение", ["Дата", "Специальность", "Приказ", "Удостоверение", "Примечание"], self.add_training, self.edit_training, self.delete_training),
            ("Оружие", ["Наименование оружия", "Номер"], self.add_weapon, self.edit_weapon, self.delete_weapon),
            ("Отсутствия", ["Категория", "Подтип", "С", "По", "Место", "Основание", "Примечание"], self.add_absence, self.edit_absence, self.delete_absence),
        ]
        for name, headers, add_handler, edit_handler, delete_handler in sections:
            tab = QWidget(); layout = QVBoxLayout(tab); hint = QLabel("Сначала сохраните карточку работника, затем можно вести записи этого раздела."); hint.setWordWrap(True); layout.addWidget(hint)
            actions = QHBoxLayout()
            for text, handler in [("Добавить", add_handler), ("Изменить", edit_handler), ("Удалить", delete_handler)]:
                button = QPushButton(text); button.clicked.connect(handler); actions.addWidget(button)
            actions.addStretch(); layout.addLayout(actions)
            table = QTableWidget(0, len(headers) + 1); table.setHorizontalHeaderLabels(["ID", *headers]); table.setColumnHidden(0, True); style_table(table); table.doubleClicked.connect(lambda *_args, section=name: self.edit_record(section)); layout.addWidget(table); self.record_tables[name] = table; self.tabs.addTab(tab, name)

    def open_record_tab(self, name: str) -> None:
        """Переключить карточку на вкладку журнала по её названию."""
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                self.tabs.setCurrentIndex(index)
                return

    def update_header(self) -> None:
        self.header_fio.setText(self.fio.text().strip() or "Новый работник")
        self.header_position.setText(f"Должность: {self.position.text().strip() or 'не указано'}")
        self.header_department.setText(f"Подразделение: {self.department.text().strip() or 'не указано'}")
        self.header_section.setText(f"Отделение: {self.section.currentText()}")
        number = self.personnel_no.text().strip() or "не указан"
        status = self.current_daily_status or (self.employment_status.currentText() if hasattr(self, "employment_status") else "—")
        self.header_meta.setText(f"Табельный №: {number}    •    Статус на сегодня: {status}")

    def update_age(self) -> None:
        age = calculate_age(iso_from_dateedit(self.birth_date, True))
        self.age_label.setText(format_age(age) if age is not None else "Не указан")

    def _status_changed(self, status: str) -> None:
        archived = status in ("Уволен", "Переведён", "Архив")
        self.archive_date.setEnabled(archived)
        if archived and self.archive_date.date() == NULL_DATE:
            self.archive_date.setDate(QDate.currentDate())
        if not archived:
            self.archive_date.setDate(NULL_DATE)

    def _apply_field_completers(self) -> None:
        def values(column: str) -> list[str]:
            try:
                return self.service.unique_field_values(column)
            except sqlite3.Error:
                return []
        attach_completer(self.department, values("department"))
        attach_completer(self.position, values("position"))
        attach_completer(self.group_label, values("group_name"))

    def form_state(self) -> tuple:
        return (
            self.fio.text(), self.personnel_no.text(), self.birth_date.date(), self.employment_date.date(),
            self.department.text(), self.section.currentText(), self.group_label.text(), self.position.text(), self.certificate_number.text(),
            self.phone.text(), self.email.text(), self.factual_address.text(), self.registration_address.text(),
            self.education.currentText(), self.schedule_type.currentText(), self.schedule_anchor.date(), self.employment_status.currentText(), self.archive_date.date(),
        )

    def save(self) -> None:
        fio, personnel_no = self.fio.text().strip(), self.personnel_no.text().strip()
        if not fio or not personnel_no:
            QMessageBox.warning(self, "Проверка", "ФИО и табельный номер обязательны.")
            return
        payload = dict(fio=fio, personnel_no=personnel_no, birth_date=iso_from_dateedit(self.birth_date, True), employment_date=iso_from_dateedit(self.employment_date, True), department=self.department.text().strip(), section=self.section.currentText(), group_name=self.group_label.text().strip(), position=self.position.text().strip(), certificate_number=self.certificate_number.text().strip(), phone=self.phone.text().strip(), email=self.email.text().strip(), factual_address=self.factual_address.text().strip(), registration_address=self.registration_address.text().strip(), education=self.education.currentText().strip(), schedule_type=self.schedule_type.currentText(), schedule_anchor=iso_from_dateedit(self.schedule_anchor, True), employment_status=self.employment_status.currentText(), archive_date=iso_from_dateedit(self.archive_date, True))
        try:
            if self.employee_id:
                self.service.update_employee(self.employee_id, **payload)
            else:
                self.employee_id = self.service.add_employee(**payload)
                self.created_in_dialog = True
            self._clean_state = self.form_state()
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Ошибка", "Табельный номер должен быть уникальным.")

    def load_employee(self) -> None:
        row = self.service.get_employee(self.employee_id); 
        if not row: return
        self.fio.setText(row['fio']); self.personnel_no.setText(row['personnel_no']); set_dateedit(self.birth_date,row['birth_date'],True); set_dateedit(self.employment_date,row['employment_date'],True); self.department.setText(row['department'] or ''); self.section.setCurrentText(row['section'] or 'Не указано'); self.group_label.setText(row['group_name'] or ''); self.position.setText(row['position'] or ''); self.certificate_number.setText(row['certificate_number'] or ''); self.phone.setText(row['phone'] or ''); self.email.setText(row['email'] or ''); self.factual_address.setText(row['factual_address'] or ''); self.registration_address.setText(row['registration_address'] or ''); self.education.setCurrentText(row['education'] or ''); self.schedule_type.setCurrentText(row['schedule_type'] or 'Не задан'); set_dateedit(self.schedule_anchor,row['schedule_anchor'],True); self.employment_status.setCurrentText(row['employment_status'] or 'Работает'); set_dateedit(self.archive_date,row['archive_date'],True); self.assignment_status.setText(row['assignment_text'] or 'Не назначен на штатную единицу'); self.current_daily_status = row['daily_status']; self.update_age(); self.update_header(); self._clean_state = self.form_state()

    def refresh_records(self) -> None:
        if not self.employee_id: return
        for name, table in self.record_tables.items():
            table.setRowCount(0)
            if name == "Медкомиссия": rows = self.service.list_medical(self.employee_id); values = lambda r: [r['id'], format_date(r['date']), r['notes']]
            elif name == "Периодическая проверка": rows = self.service.list_periodic(self.employee_id); values = lambda r: [r['id'], format_date(r['date']), r['result'], r['notes']]
            elif name == "Обучение": rows = self.service.list_training(self.employee_id); values = lambda r: [r['id'], format_date(r['date']), r['specialty'], r['order_info'], r['certificate'], r['notes']]
            elif name == "Оружие": rows = self.service.list_weapons(self.employee_id); values = lambda r: [r['id'], r['weapon_name'], r['weapon_number']]
            else: rows = self.service.list_employee_events(self.employee_id); values = lambda r: [r['id'], r['event_type'], r['subtype'], format_date(r['start_date']), format_date(r['end_date']), r['location'], r['basis'], r['notes']]
            for r in rows:
                row = table.rowCount(); table.insertRow(row)
                for col, value in enumerate(values(r)): table.setItem(row, col, QTableWidgetItem(str(value or '')))

    def _selected_record_id(self, name: str) -> int | None:
        table = self.record_tables[name]; row = table.currentRow()
        return int(table.item(row, 0).text()) if row >= 0 and table.item(row, 0) else None

    def add_medical(self):
        if not self.employee_id: return
        dialog = MedicalDialog(self.service, self.employee_id, parent=self)
        if dialog.exec(): self.refresh_records()
    def edit_medical(self):
        record_id = self._selected_record_id("Медкомиссия")
        if record_id:
            if MedicalDialog(self.service, self.employee_id, record_id, self).exec(): self.refresh_records()
    def delete_medical(self): self.delete_record("Медкомиссия")
    def add_periodic(self):
        if not self.employee_id: return
        dialog = PeriodicDialog(self.service, self.employee_id, parent=self)
        if dialog.exec(): self.refresh_records()
    def edit_periodic(self):
        record_id = self._selected_record_id("Периодическая проверка")
        if record_id:
            if PeriodicDialog(self.service, self.employee_id, record_id, self).exec(): self.refresh_records()
    def delete_periodic(self): self.delete_record("Периодическая проверка")
    def add_training(self):
        if not self.employee_id: return
        dialog = TrainingDialog(self.service, self.employee_id, parent=self)
        if dialog.exec(): self.refresh_records()
    def edit_training(self):
        record_id = self._selected_record_id("Обучение")
        if record_id:
            if TrainingDialog(self.service, self.employee_id, record_id, self).exec(): self.refresh_records()
    def delete_training(self): self.delete_record("Обучение")
    def add_weapon(self):
        if not self.employee_id: return
        dialog = WeaponDialog(self.service, self.employee_id, parent=self)
        if dialog.exec(): self.refresh_records()
    def edit_weapon(self):
        record_id = self._selected_record_id("Оружие")
        if record_id:
            if WeaponDialog(self.service, self.employee_id, record_id, self).exec(): self.refresh_records()
    def delete_weapon(self): self.delete_record("Оружие")
    def add_absence(self):
        if not self.employee_id: return
        dialog = EventDialog(self.service, self, employee_id=self.employee_id)
        if dialog.exec(): self.refresh_records()
    def edit_absence(self):
        record_id = self._selected_record_id("Отсутствия")
        if record_id:
            if EventDialog(self.service, self, employee_id=self.employee_id, event_id=record_id).exec(): self.refresh_records()
    def delete_absence(self): self.delete_record("Отсутствия")

    def edit_record(self, name: str) -> None:
        mapping = {"Медкомиссия": self.edit_medical, "Периодическая проверка": self.edit_periodic,
                   "Обучение": self.edit_training, "Оружие": self.edit_weapon, "Отсутствия": self.edit_absence}
        mapping[name]()

    def delete_record(self, name: str) -> None:
        record_id = self._selected_record_id(name)
        if not record_id: return
        if QMessageBox.question(self, "Удаление", "Удалить выбранную запись?") != QMessageBox.Yes: return
        if name == "Медкомиссия": self.service.delete_medical(record_id)
        elif name == "Периодическая проверка": self.service.delete_periodic(record_id)
        elif name == "Обучение": self.service.delete_training(record_id)
        elif name == "Оружие": self.service.delete_weapon(record_id)
        else: self.service.delete_event(record_id)
        self.refresh_records()

    def choose_photo(self) -> None:
        if not self.employee_id:
            QMessageBox.information(self, "Фото", "Сначала сохраните карточку работника.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Выберите фотографию", "", "Изображения (*.png *.jpg *.jpeg)")
        if not filename: return
        try:
            self.service.set_employee_photo(self.employee_id, filename)
            self.load_photo()
        except ValueError as exc: QMessageBox.warning(self, "Фото", str(exc))

    def delete_photo(self) -> None:
        if self.employee_id and QMessageBox.question(self, "Фото", "Удалить фотографию?") == QMessageBox.Yes:
            self.service.delete_employee_photo(self.employee_id); self.load_photo()

    def load_photo(self) -> None:
        path = self.service.employee_photo_path(self.employee_id) if self.employee_id else None
        if not path or not path.exists(): self.photo.setPixmap(QPixmap()); self.photo.setText("ФОТО"); return
        pix = QPixmap(str(path)); self.photo.setPixmap(pix.scaled(self.photo.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)); self.photo.setText("")

    def show_photo(self) -> None:
        path = self.service.employee_photo_path(self.employee_id) if self.employee_id else None
        if not path or not path.exists(): return
        dialog=QDialog(self); dialog.setWindowTitle("Фотография"); layout=QVBoxLayout(dialog); label=QLabel(); pix=QPixmap(str(path)); label.setPixmap(pix.scaled(700,700,Qt.KeepAspectRatio,Qt.SmoothTransformation)); layout.addWidget(label); close=QPushButton("Закрыть"); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def copy_employee_data(self, index: int) -> None:
        if index <= 0: return
        labels = [self.fio.text(), f"{self.fio.text()} — таб. № {self.personnel_no.text()}", self.phone.text(), self.position.text()]
        QApplication.clipboard().setText(labels[index - 1]); self.copy_data.setCurrentIndex(0)

    def closeEvent(self, event) -> None:
        if self.form_state() != self._clean_state:
            answer = QMessageBox.question(self, "Несохранённые изменения", "Закрыть без сохранения?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes: event.ignore(); return
        event.accept()


class StaffUnitDialog(QDialog):
    def __init__(self, service: PersonnelService, unit_id: int | None = None, parent=None, employee_id: int | None = None, vacancies_only: bool = False):
        super().__init__(parent); self.service,self.unit_id,self.employee_id,self.vacancies_only=service,unit_id,employee_id,vacancies_only; self.setWindowTitle("Штатная единица")
        layout=QFormLayout(self); self.unit_number=QLineEdit(); self.department=QLineEdit(); self.section=QComboBox(); self.section.setEditable(True); self.section.addItems(SECTIONS); self.group=QLineEdit(); self.position=QLineEdit(); self.employee=QComboBox()
        attach_completer(self.department, self.service.unique_field_values("department")); attach_completer(self.group, self.service.unique_field_values("group_name")); attach_completer(self.position, self.service.unique_field_values("position"))
        self.employee.addItem("Вакансия",None)
        for p in self.service.list_employees():
            self.employee.addItem(f"{p['fio']} ({p['personnel_no']})",p['id'])
        layout.addRow("№ штатной единицы*",self.unit_number); layout.addRow("Отдел",self.department); layout.addRow("Отделение",self.section); layout.addRow("Группа",self.group); layout.addRow("Должность*",self.position); layout.addRow("Работник",self.employee)
        buttons=russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addRow(buttons)
        if unit_id: self.load()
        if employee_id is not None:
            index=self.employee.findData(employee_id)
            if index>=0: self.employee.setCurrentIndex(index)
            self.employee.setEnabled(False)
    def load(self):
        row=self.service.staff_unit(self.unit_id); self.unit_number.setText(row['unit_number']); self.department.setText(row['department']); self.section.setCurrentText(row['section']); self.group.setText(row['group_name']); self.position.setText(row['position']); idx=self.employee.findData(row['employee_id']); self.employee.setCurrentIndex(max(0,idx))
    def save(self):
        try:
            if self.employee_id is not None:
                selected_employee=self.employee_id
            else:
                selected_employee=self.employee.currentData()
            if not self.unit_number.text().strip() or not self.position.text().strip(): QMessageBox.warning(self,"Проверка","№ штатной единицы и должность обязательны."); return
            if self.unit_id: self.service.update_staff_unit(self.unit_id,self.unit_number.text().strip(),self.department.text().strip(),self.section.currentText(),self.group.text().strip(),self.position.text().strip(),selected_employee)
            else: self.unit_id=self.service.add_staff_unit(self.unit_number.text().strip(),self.department.text().strip(),self.section.currentText(),self.group.text().strip(),self.position.text().strip(),selected_employee)
            self.accept()
        except sqlite3.IntegrityError: QMessageBox.warning(self,"Ошибка","Номер штатной единицы должен быть уникальным, а работник не может занимать две единицы.")


class EventDialog(QDialog):
    def __init__(self, service: PersonnelService, parent=None, employee_id: int | None = None, event_id: int | None = None):
        super().__init__(parent); self.service,self.event_id=service,event_id; self.setWindowTitle("Событие / отсутствие"); self.setMinimumWidth(520)
        f=QFormLayout(self); self.employee=QComboBox();
        for p in service.list_employees(): self.employee.addItem(f"{p['fio']} ({p['personnel_no']})",p['id'])
        if employee_id:
            idx=self.employee.findData(employee_id); self.employee.setCurrentIndex(max(0,idx)); self.employee.setEnabled(False)
        self.type=QComboBox(); self.type.addItems(EVENT_TYPES.keys()); self.subtype=QComboBox(); self.start=new_date_edit(); self.end=new_date_edit(); self.location=QLineEdit(); self.basis=QLineEdit(); self.notes=QTextEdit(); self.notes.setFixedHeight(90)
        self.type.currentTextChanged.connect(self.update_subtypes); self.update_subtypes(self.type.currentText())
        f.addRow("Работник",self.employee); f.addRow("Категория",self.type); f.addRow("Подтип",self.subtype); f.addRow("С",self.start); f.addRow("По",self.end); f.addRow("Место / объект",self.location); f.addRow("Основание",self.basis); f.addRow("Примечание",self.notes)
        buttons=russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); f.addRow(buttons)
        if event_id: self.load()
    def update_subtypes(self, event_type: str): self.subtype.clear(); self.subtype.addItems(["",*EVENT_TYPES.get(event_type,[])])
    def load(self):
        row=self.service.get_event(self.event_id); self.employee.setCurrentIndex(max(0,self.employee.findData(row['employee_id']))); self.type.setCurrentText(row['event_type']); self.update_subtypes(row['event_type']); self.subtype.setCurrentText(row['subtype']); set_dateedit(self.start,row['start_date']); set_dateedit(self.end,row['end_date']); self.location.setText(row['location']); self.basis.setText(row['basis']); self.notes.setPlainText(row['notes'])
    def save(self):
        try:
            if not self.employee.currentData(): QMessageBox.warning(self,"Проверка","Выберите работника."); return
            if self.end.date()<self.start.date(): QMessageBox.warning(self,"Проверка","Дата окончания не может быть раньше даты начала."); return
            payload=dict(employee_id=self.employee.currentData(),event_type=self.type.currentText(),subtype=self.subtype.currentText(),start_date=iso_from_dateedit(self.start),end_date=iso_from_dateedit(self.end),location=self.location.text().strip(),basis=self.basis.text().strip(),notes=self.notes.toPlainText().strip())
            if self.event_id: self.service.update_event(self.event_id,**payload)
            else: self.service.add_event(**payload)
            self.accept()
        except sqlite3.IntegrityError: QMessageBox.warning(self,"Ошибка","Такое событие уже существует.")


class MedicalDialog(QDialog):
    def __init__(self, service, employee_id, record_id=None, parent=None): super().__init__(parent); self.service,self.employee_id,self.record_id=service,employee_id,record_id; self.setWindowTitle("Медкомиссия"); f=QFormLayout(self); self.date=new_date_edit(); self.notes=QLineEdit(); f.addRow("Дата",self.date); f.addRow("Примечание",self.notes); buttons=russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); f.addRow(buttons); self.load() if record_id else None
    def load(self): row=self.service.get_medical(self.record_id); set_dateedit(self.date,row['date']); self.notes.setText(row['notes'])
    def save(self):
        payload=(self.employee_id,iso_from_dateedit(self.date),self.notes.text().strip()); self.service.save_medical(self.record_id,*payload); self.accept()


class PeriodicDialog(QDialog):
    def __init__(self, service, employee_id, record_id=None, parent=None): super().__init__(parent); self.service,self.employee_id,self.record_id=service,employee_id,record_id; self.setWindowTitle("Периодическая проверка"); f=QFormLayout(self); self.date=new_date_edit(); self.result=QLineEdit(); self.notes=QLineEdit(); f.addRow("Дата",self.date); f.addRow("Результат",self.result); f.addRow("Примечание",self.notes); buttons=russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); f.addRow(buttons); self.load() if record_id else None
    def load(self): row=self.service.get_periodic(self.record_id); set_dateedit(self.date,row['date']); self.result.setText(row['result']); self.notes.setText(row['notes'])
    def save(self): payload=(self.employee_id,iso_from_dateedit(self.date),self.result.text().strip(),self.notes.text().strip()); self.service.save_periodic(self.record_id,*payload); self.accept()


class TrainingDialog(QDialog):
    def __init__(self, service, employee_id, record_id=None, parent=None): super().__init__(parent); self.service,self.employee_id,self.record_id=service,employee_id,record_id; self.setWindowTitle("Обучение"); f=QFormLayout(self); self.date=new_date_edit(); self.specialty=QLineEdit(); self.order=QLineEdit(); self.certificate=QLineEdit(); self.notes=QLineEdit(); f.addRow("Дата",self.date); f.addRow("Специальность",self.specialty); f.addRow("Приказ",self.order); f.addRow("Удостоверение",self.certificate); f.addRow("Примечание",self.notes); buttons=russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); f.addRow(buttons); self.load() if record_id else None
    def load(self): row=self.service.get_training(self.record_id); set_dateedit(self.date,row['date']); self.specialty.setText(row['specialty']); self.order.setText(row['order_info']); self.certificate.setText(row['certificate']); self.notes.setText(row['notes'])
    def save(self): payload=(self.employee_id,iso_from_dateedit(self.date),self.specialty.text().strip(),self.order.text().strip(),self.certificate.text().strip(),self.notes.text().strip()); self.service.save_training(self.record_id,*payload); self.accept()


class WeaponDialog(QDialog):
    def __init__(self, service, employee_id, record_id=None, parent=None): super().__init__(parent); self.service,self.employee_id,self.record_id=service,employee_id,record_id; self.setWindowTitle("Оружие"); f=QFormLayout(self); self.weapon=QLineEdit(); self.number=QLineEdit(); f.addRow("Наименование",self.weapon); f.addRow("Номер",self.number); buttons=russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); f.addRow(buttons); self.load() if record_id else None
    def load(self): row=self.service.get_weapon(self.record_id); self.weapon.setText(row['weapon_name']); self.number.setText(row['weapon_number'])
    def save(self): payload=(self.employee_id,self.weapon.text().strip(),self.number.text().strip()); self.service.save_weapon(self.record_id,*payload); self.accept()


class UnassignedEmployeesDialog(QDialog):
    def __init__(self, service: PersonnelService, parent=None):
        super().__init__(parent); self.service=service; self.setWindowTitle("Не назначены на штатную единицу"); self.resize(820,460)
        layout=QVBoxLayout(self); self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["ID","ФИО","Таб. №","Подразделение","Должность"]); self.table.setColumnHidden(0,True); style_table(self.table); layout.addWidget(self.table); actions=QHBoxLayout(); self.assign=QPushButton("Назначить на ШЕ"); self.assign.clicked.connect(self.assign_selected); actions.addWidget(self.assign); actions.addStretch(); layout.addLayout(actions); close=QPushButton("Закрыть"); close.clicked.connect(self.accept); layout.addWidget(close); self.refresh()
    def refresh(self):
        rows=self.service.unassigned_active_employees(); self.table.setRowCount(len(rows))
        for i,p in enumerate(rows):
            for j,v in enumerate([p['id'],p['fio'],p['personnel_no'],p['department'],p['position']]): self.table.setItem(i,j,QTableWidgetItem(str(v or '—')))
    def assign_selected(self):
        row=self.table.currentRow()
        if row<0: return
        emp_id=int(self.table.item(row,0).text()); vacancies=[u for u in self.service.list_staff_units() if not u['employee_id']]
        if not vacancies: QMessageBox.information(self,"Вакансии","Свободных штатных единиц нет."); return
        selector=QDialog(self); selector.setWindowTitle("Выберите вакансию"); form=QFormLayout(selector); combo=QComboBox(); [combo.addItem(f"{u['unit_number']} — {u['section']}, {u['position']}",u['id']) for u in vacancies]; form.addRow("Вакантная единица",combo); buttons=russian_dialog_buttons("Назначить"); buttons.accepted.connect(selector.accept); buttons.rejected.connect(selector.reject); form.addRow(buttons)
        if selector.exec(): StaffUnitDialog(self.service,combo.currentData(),self,employee_id=emp_id,vacancies_only=True).exec(); self.refresh()


class ColumnFilterMenu(QMenu):
    pass


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path):
        super().__init__(); self.db=Database(db_path); self.service=PersonnelService(self.db); self.settings=QSettings("PersonnelTracker","PersonnelTracker"); self.theme_manager=ThemeManager(self.settings)
        self.setWindowTitle(APP_NAME); self.resize(1200,760); self.setMinimumSize(760,520); self.staff_sort=(1,Qt.AscendingOrder)
        self.staff_column_order=[]
        self.staff_hidden_columns=set()
        self.staff_filters={}
        self.sidebar_buttons=[]; self.page_buttons=QButtonGroup(self); self.page_buttons.setExclusive(True); self.pages=QStackedWidget(); self._build_menu(); self._build_shell(); self._build_staff_page(); self._build_events_page(); self._build_summary_page(); self._build_employees_page(); self._build_service_page(); self.page_buttons.buttonClicked.connect(self.switch_page); self.sidebar_buttons[0].setChecked(True); self.refresh_all()

    def _build_menu(self):
        menu=self.menuBar().addMenu("Сервис")
        show_employees=QAction("Работники",self); show_employees.triggered.connect(lambda: self.pages.setCurrentIndex(3)); menu.addAction(show_employees)
        show_archive=QAction("Архив работников",self); show_archive.triggered.connect(self.show_archive); menu.addAction(show_archive)
        show_unassigned=QAction("Не назначены на штатную единицу",self); show_unassigned.triggered.connect(self.show_unassigned); menu.addAction(show_unassigned)
        menu.addSeparator(); exit_action=QAction("Выход",self); exit_action.triggered.connect(self.close); menu.addAction(exit_action)

    def _build_shell(self):
        central=QWidget(); self.setCentralWidget(central); root=QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(200); side=QVBoxLayout(sidebar); side.setContentsMargins(10,10,10,10); side.setSpacing(6)
        title=QLabel("PersonnelTracker"); title.setObjectName("appTitle"); subtitle=QLabel("v0.6 · локальная кадровая система"); subtitle.setObjectName("appSubtitle"); side.addWidget(title); side.addWidget(subtitle)
        for index,text in enumerate(["ШДС","События","Расход","Работники","Сервис"]):
            b=QPushButton(text); b.setCheckable(True); b.setProperty("navButton",True); self.page_buttons.addButton(b,index); self.sidebar_buttons.append(b); side.addWidget(b)
        side.addStretch(); theme=QPushButton("◐  Тема"); theme.clicked.connect(self.toggle_theme); side.addWidget(theme); root.addWidget(side)
        content=QWidget(); content_root=QVBoxLayout(content); content_root.setContentsMargins(18,14,18,14); content_root.addWidget(self.pages); root.addWidget(content,1)

    def _page(self,title):
        page=QWidget(); root=QVBoxLayout(page); root.setSpacing(10); header=QLabel(title); header.setObjectName("pageTitle"); root.addWidget(header); return page,root
    def _add_page(self,page): self.pages.addWidget(page)
    def switch_page(self,button): self.pages.setCurrentIndex(self.page_buttons.id(button))
    def toggle_theme(self):
        self.theme_manager.toggle(QApplication.instance()); self._sync_theme_controls(); self.refresh_all()
    def _sync_theme_controls(self):
        dark=self.theme_manager.current_theme()==ThemeManager.DARK
        if hasattr(self,'theme_status_label'): self.theme_status_label.setText("Тёмная" if dark else "Светлая")

    def _build_service_page(self):
        page, root = self._page("Сервис")
        appearance = QGroupBox("Оформление")
        form = QHBoxLayout(appearance)
        form.addWidget(QLabel("Текущая тема:"))
        self.theme_status_label = QLabel()
        form.addWidget(self.theme_status_label)
        toggle = QPushButton("Переключить светлую/тёмную тему")
        toggle.clicked.connect(self.toggle_theme)
        form.addWidget(toggle)
        form.addStretch()
        root.addWidget(appearance)
        data = QGroupBox("Данные")
        data_layout = QHBoxLayout(data)
        demo = QPushButton("Добавить демо-данные")
        demo.clicked.connect(self.seed_demo)
        path = QPushButton("Показать путь к данным")
        path.clicked.connect(self.show_data_path)
        data_layout.addWidget(demo)
        data_layout.addWidget(path)
        data_layout.addStretch()
        root.addWidget(data)
        root.addStretch()
        self._add_page(page)
        self._sync_theme_controls()

    def _build_employees_page(self):
        page, root = self._page("Личный состав")
        top = QHBoxLayout(); self.emp_search = QLineEdit(); self.emp_search.setPlaceholderText("Фамилия, табельный номер, подразделение, должность..."); self.emp_search.textChanged.connect(self.refresh_employees); add = QPushButton("Добавить работника"); add.setProperty("role", "primary"); add.clicked.connect(self.add_employee); edit = QPushButton("Открыть карточку"); edit.clicked.connect(self.edit_employee); top.addWidget(QLabel("Поиск:")); top.addWidget(self.emp_search, 1); top.addWidget(add); top.addWidget(edit); root.addLayout(top); self.emp_table = QTableWidget(0, 6); self.emp_table.setHorizontalHeaderLabels(["ID", "ФИО", "Таб. №", "Подразделение", "Должность", "График"]); self.emp_table.setColumnHidden(0, True); style_table(self.emp_table); self.emp_table.doubleClicked.connect(self.edit_employee); root.addWidget(self.emp_table); self._add_page(page)

    def _metric_card(self, caption: str) -> QLabel:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        caption_label = QLabel(caption)
        caption_label.setObjectName("metricCaption")
        value = QLabel("—")
        value.setObjectName("metricValue")
        layout.addWidget(caption_label)
        layout.addWidget(value)
        self.staff_metrics_cards.addWidget(card)
        return value

    def _build_staff_page(self):
        page, root = self._page("Штатно-должностная книга")

        # Карточки показателей: По штату / По списку / Вакансии / Показано.
        self.staff_metrics_cards = QHBoxLayout()
        self.staff_metrics_cards.setSpacing(10)
        self.metric_staff = self._metric_card("По штату")
        self.metric_listed = self._metric_card("По списку")
        self.metric_vacant = self._metric_card("Вакансии")
        self.metric_shown = self._metric_card("Показано")
        self.staff_metrics_cards.addStretch()
        root.addLayout(self.staff_metrics_cards)
        # Исходный текстовый индикатор сохранён для совместимости (smoke-тест),
        # на экране его заменяют карточки выше.
        self.staff_metrics_label = QLabel()
        self.staff_metrics_label.hide()
        root.addWidget(self.staff_metrics_label)
        self.staff_warning_label = QLabel()
        self.staff_warning_label.setObjectName("warningText")
        root.addWidget(self.staff_warning_label)

        top = QHBoxLayout()
        self.staff_section = QComboBox(); self.staff_section.addItems(["Все", *SECTIONS]); self.staff_section.currentTextChanged.connect(self.refresh_staff)
        self.staff_search = QLineEdit(); self.staff_search.setPlaceholderText("ФИО, табельный номер, должность, телефон или № штатной единицы..."); self.staff_search.textChanged.connect(self.refresh_staff)
        add_employee = QPushButton("Добавить работника"); add_employee.setProperty("role", "primary"); add_employee.clicked.connect(self.add_employee)
        add = QPushButton("Добавить ШЕ"); add.setToolTip("Добавить штатную единицу"); add.clicked.connect(self.add_staff)
        edit = QPushButton("Изменить"); edit.clicked.connect(self.edit_staff)
        actions = QMenu(self)
        for text, handler in (("Удалить единицу", self.delete_staff), ("Архив работников", self.show_archive), ("Не назначены на штатную единицу", self.show_unassigned), ("Назначить нескольким", self.assign_batch_from_staff), ("Настроить колонки", self.show_column_menu), ("Сбросить фильтры", self.reset_staff_filters)):
            action = actions.addAction(text); action.triggered.connect(handler)
        more = QToolButton(); more.setText("Действия ▼"); more.setMenu(actions); more.setPopupMode(QToolButton.InstantPopup)
        top.addWidget(QLabel("Отделение:")); top.addWidget(self.staff_section); top.addWidget(QLabel("Поиск:")); top.addWidget(self.staff_search, 1)
        for button in (add_employee, add, edit, more):
            top.addWidget(button)
        root.addLayout(top)

        self.staff_headers = ["ID", "№", "Отдел", "Отделение", "Группа", "Должность", "ФИО", "Таб. №", "Дата рождения", "Возраст", "Телефон", "Вооружение", "Email", "Дата приёма", "Последняя МК", "Последняя ПП", "График"]
        self.staff_filters: dict[str, set[str]] = {}
        self.staff_table = SpreadsheetTable(0, len(self.staff_headers)); self.staff_table.setHorizontalHeaderLabels(self.staff_headers); self.staff_table.setColumnHidden(0, True); style_table(self.staff_table); self.staff_table.setSelectionMode(QTableWidget.ExtendedSelection)
        header = self.staff_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self.sort_staff_by_column)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.open_staff_filter_menu)
        header.sectionResized.connect(self.save_staff_layout)
        self.staff_table.doubleClicked.connect(self.open_staff_row)
        # All visible SHDS columns remain user-resizable. Position and FIO start
        # wider for readability, but no longer use Stretch mode, which blocked
        # manual resizing on macOS.
        self._apply_default_staff_column_sizes()
        self._restore_staff_layout()
        root.addWidget(self.staff_table)
        self._add_page(page)

    def _apply_default_staff_column_sizes(self) -> None:
        widths = {"№": 64, "Отдел": 110, "Отделение": 110, "Группа": 90,
                  "Должность": 180, "ФИО": 220, "Таб. №": 80,
                  "Дата рождения": 110, "Возраст": 70, "Телефон": 130, "Вооружение": 120,
                  "Email": 160, "Дата приёма": 100, "Последняя МК": 110, "Последняя ПП": 110, "График": 90}
        for index, name in enumerate(self.staff_headers):
            if name in widths:
                self.staff_table.setColumnWidth(index, widths[name])

    def _build_events_page(self):
        page, root = self._page("Занятость и отсутствия")
        top = QHBoxLayout(); self.event_search = QLineEdit(); self.event_search.setPlaceholderText("Поиск по работнику или событию..."); self.event_search.textChanged.connect(self.refresh_events); add = QPushButton("Добавить"); add.setProperty("role", "primary"); add.clicked.connect(self.add_event); batch = QPushButton("Назначить нескольким"); batch.clicked.connect(self.assign_batch); edit = QPushButton("Изменить"); edit.clicked.connect(self.edit_event); group = QPushButton("Открыть группу"); group.clicked.connect(self.open_selected_group); delete = QPushButton("Удалить"); delete.setProperty("role", "danger"); delete.clicked.connect(self.delete_event); top.addWidget(QLabel("Поиск:")); top.addWidget(self.event_search, 1); top.addWidget(add); top.addWidget(batch); top.addWidget(edit); top.addWidget(group); top.addWidget(delete); root.addLayout(top); self.event_table = QTableWidget(0, 8); self.event_table.setHorizontalHeaderLabels(["ID", "Работник", "Категория", "Подтип", "С", "По", "Место", "Основание"]); self.event_table.setColumnHidden(0, True); style_table(self.event_table); self.event_table.doubleClicked.connect(self.edit_event); root.addWidget(self.event_table); self._add_page(page)

    def _build_summary_page(self):
        page, root = self._page("Расход")
        views = QTabWidget(); root.addWidget(views)
        summary_tab = QWidget(); summary_root = QVBoxLayout(summary_tab); top = QHBoxLayout(); self.summary_date = new_date_edit(); self.summary_date.setDate(QDate.currentDate()); self.summary_date.dateChanged.connect(self.refresh_summary); self.summary_section = QComboBox(); self.summary_section.addItems(["Все", *SECTIONS[:-1]]); self.summary_section.currentTextChanged.connect(self.refresh_summary); refresh = QPushButton("Пересчитать"); refresh.clicked.connect(self.refresh_summary); copy = QPushButton("Копировать расход"); copy.setProperty("role", "primary"); copy.clicked.connect(self.copy_summary); top.addWidget(QLabel("Дата расхода:")); top.addWidget(self.summary_date); top.addWidget(QLabel("Подробный расход:")); top.addWidget(self.summary_section); top.addWidget(refresh); top.addStretch(); top.addWidget(copy); summary_root.addLayout(top)
        self.summary_table = QTableWidget(5, 6); self.summary_table.setHorizontalHeaderLabels(["Показатель", "Всего", "Руководство", "1 отделение", "2 отделение", "Не указано"]); self.summary_table.setVerticalHeaderLabels([]); style_table(self.summary_table); self.summary_table.cellClicked.connect(self.open_metric_people); summary_root.addWidget(self.summary_table)
        self.diagnostic_label = QLabel(); self.diagnostic_label.setObjectName("warningText"); summary_root.addWidget(self.diagnostic_label)
        splitter = QHBoxLayout(); self.summary_tree = QTreeWidget(); self.summary_tree.setHeaderLabels(["Категория", "Количество"]); self.summary_tree.itemClicked.connect(self.show_group_members); self.summary_people = QTableWidget(0, 4); self.summary_people.setHorizontalHeaderLabels(["ФИО", "Таб. №", "Должность", "Источник"]); style_table(self.summary_people); splitter.addWidget(self.summary_tree, 1); splitter.addWidget(self.summary_people, 2); summary_root.addLayout(splitter, 1); views.addTab(summary_tab, "Сводка")
        state_tab = QWidget(); state_root = QVBoxLayout(state_tab); state_top = QHBoxLayout(); self.state_date = new_date_edit(); self.state_date.setDate(QDate.currentDate()); self.state_date.dateChanged.connect(self.refresh_state); state_top.addWidget(QLabel("Дата:")); state_top.addWidget(self.state_date); state_refresh = QPushButton("Показать"); state_refresh.clicked.connect(self.refresh_state); state_top.addWidget(state_refresh); state_top.addStretch(); state_root.addLayout(state_top); self.state_table = QTableWidget(0, 7); self.state_table.setHorizontalHeaderLabels(["№", "ФИО", "Отделение", "Группа", "Должность", "Состояние", "Причина / мероприятие"]); style_table(self.state_table); state_root.addWidget(self.state_table); views.addTab(state_tab, "Состояние на дату"); self._add_page(page)
    def refresh_all(self): self.refresh_staff(); self.refresh_events(); self.refresh_summary(); self.refresh_state()
    CONTROL_PERIOD_DAYS = 365
    CONTROL_WARNING_DAYS = 30

    def _control_color(self, value: str | None):
        if not value or value == "—":
            return None
        parsed = QDate.fromString(value, "yyyy-MM-dd")
        if not parsed.isValid():
            return None
        days = parsed.daysTo(QDate.currentDate())
        if days > self.CONTROL_PERIOD_DAYS:
            return self.theme_manager.color("error")
        if days > self.CONTROL_PERIOD_DAYS - self.CONTROL_WARNING_DAYS:
            return self.theme_manager.color("warning")
        return None

    def refresh_staff(self):
        if not hasattr(self,'staff_table'): return
        rows=self.service.list_staff_units(self.staff_section.currentText(),self.staff_search.text(),self.staff_filters); self.staff_table.setRowCount(len(rows))
        vacancy_bg = self.theme_manager.color("vacancy_bg")
        vacancy_fg = self.theme_manager.color("vacancy_text")
        attention_bg = self.theme_manager.color("attention_bg")
        med_col = self.staff_headers.index("Последняя МК")
        periodic_col = self.staff_headers.index("Последняя ПП")
        for i,u in enumerate(rows):
            employee=self.service.get_employee(int(u['employee_id'])) if u['employee_id'] and u['employment_status']=='Работает' else None; birth=employee['birth_date'] if employee else None; age=calculate_age(birth) if birth else None
            med, periodic = self.service.latest_check_dates(int(u['employee_id'])) if employee else (None, None)
            values=[u['id'],u['unit_number'],u['department'] or '—',u['section'] or 'Не указано',u['group_name'] or '—',u['position'],employee['fio'] if employee else 'ВАКАНСИЯ',(employee['personnel_no'] if employee else '') or '—',birth or '—',str(age) if age is not None else '—',(employee['phone'] if employee else '') or '—',self.service.weapon_summary(int(u['employee_id'])) if employee else '—',(employee['email'] if employee else '') or '—',(employee['employment_date'] if employee else '') or '—',med or '—',periodic or '—',(employee['schedule_type'] if employee else '') or '—']
            keys=[(0,int(u['id'])),(1,natural_sort_key(u['unit_number'])),None,None,None,None,None,(1,natural_sort_key(employee['personnel_no'])) if employee else (2,),(0,birth) if birth else (2,),(0,age) if age is not None else (2,),None,None,None,(0,employee['employment_date']) if employee and employee['employment_date'] else (2,),(0,med) if med else (2,),(0,periodic) if periodic else (2,),None]
            for j,v in enumerate(values):
                item=QTableWidgetItem(str(v or ''))
                if keys[j] is not None: item.setData(Qt.UserRole,keys[j])
                if not employee:
                    item.setBackground(vacancy_bg)
                    item.setForeground(vacancy_fg)
                if j == 3 and u['section'] == 'Не указано':
                    item.setBackground(attention_bg)
                if employee and j in (med_col, periodic_col):
                    control_color = self._control_color(str(v or ''))
                    if control_color is not None:
                        item.setForeground(control_color)
                self.staff_table.setItem(i,j,item)
        self._apply_staff_sort(); self._update_staff_header_markers()
        metrics_all=self.service.staff_metrics(date.today().isoformat())['total']; undistributed=self.service.staff_metrics(date.today().isoformat(),"Не указано")['total']['staff']
        self.metric_staff.setText(str(metrics_all['staff']))
        self.metric_listed.setText(str(metrics_all['listed']))
        self.metric_vacant.setText(str(metrics_all['vacant']))
        self.metric_shown.setText(str(len(rows)))
        self.staff_warning_label.setText(f"Не распределено по отделениям: {undistributed}" if undistributed else "")
        text=f"ПО ШТАТУ: {metrics_all['staff']}     ПО СПИСКУ: {metrics_all['listed']}     ВАКАНСИИ: {metrics_all['vacant']}     ПОКАЗАНО: {len(rows)}"
        self.staff_metrics_label.setText(text)
    def reset_staff_filters(self):
        self.staff_section.setCurrentText("Все"); self.staff_search.clear(); self.staff_filters.clear(); self.staff_sort=(1,Qt.AscendingOrder); self.refresh_staff()
    def sort_staff_by_column(self,column):
        if column == 0: return
        if self.staff_sort[0] == column: self.staff_sort=(column,Qt.DescendingOrder if self.staff_sort[1]==Qt.AscendingOrder else Qt.AscendingOrder)
        else: self.staff_sort=(column,Qt.AscendingOrder)
        self._apply_staff_sort(); self._update_staff_header_markers()
    def _apply_staff_sort(self):
        if self.staff_table.rowCount()==0:return
        column,order=self.staff_sort; items=[]
        for row in range(self.staff_table.rowCount()):
            item=self.staff_table.item(row,column); key=item.data(Qt.UserRole) if item and item.data(Qt.UserRole) is not None else ((1,natural_sort_key(item.text())) if item and item.text() not in ('—','') else (2,)); values=[self.staff_table.takeItem(row,col) for col in range(self.staff_table.columnCount())]; items.append((key,values))
        items.sort(key=lambda pair:pair[0],reverse=order==Qt.DescendingOrder)
        for row,(_,values) in enumerate(items):
            for col,item in enumerate(values): self.staff_table.setItem(row,col,item)
    def _update_staff_header_markers(self):
        for column,base in enumerate(self.staff_headers):
            item=self.staff_table.horizontalHeaderItem(column)
            if item:
                marker=""; 
                if column==self.staff_sort[0]: marker=" ↑" if self.staff_sort[1]==Qt.AscendingOrder else " ↓"
                if base in self.staff_filters and self.staff_filters[base]: marker += " ●"
                item.setText(base+marker)
    def open_staff_filter_menu(self,pos):
        header=self.staff_table.horizontalHeader(); col=header.logicalIndexAt(pos)
        if col<=0:return
        name=self.staff_headers[col]; values=[]
        for row in range(self.staff_table.rowCount()):
            text=self.staff_table.item(row,col).text() if self.staff_table.item(row,col) else ''
            if text not in values: values.append(text)
        menu=QMenu(self); all_action=menu.addAction("Все"); menu.addSeparator(); checks=[]
        active=self.staff_filters.get(name,set())
        for value in sorted(values,key=natural_sort_key):
            action=menu.addAction(value or '(пусто)'); action.setCheckable(True); action.setChecked(not active or value in active); checks.append((action,value))
        def apply():
            selected={value for action,value in checks if action.isChecked()}
            self.staff_filters.pop(name,None) if len(selected)==len(checks) else self.staff_filters.__setitem__(name,selected); self.refresh_staff()
        for action,_ in checks: action.triggered.connect(apply)
        all_action.triggered.connect(lambda: (self.staff_filters.pop(name,None),self.refresh_staff()))
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def _restore_staff_layout(self):
        try:
            visible=json.loads(self.db.get_setting('shds_visible_columns','{}'))
            widths=json.loads(self.db.get_setting('shds_column_widths','{}'))
        except json.JSONDecodeError:
            visible, widths = {}, {}
        for index, header in enumerate(self.staff_headers[1:], 1):
            if header in visible: self.staff_table.setColumnHidden(index, not bool(visible[header]))
            if header in widths:
                self.staff_table.setColumnWidth(index, max(80, min(int(widths[header]), 320)))

    def save_staff_layout(self, *_args):
        visible={header:not self.staff_table.isColumnHidden(index) for index,header in enumerate(self.staff_headers[1:],1)}
        widths={header:self.staff_table.columnWidth(index) for index,header in enumerate(self.staff_headers[1:],1)}
        self.db.set_setting('shds_visible_columns',json.dumps(visible,ensure_ascii=False)); self.db.set_setting('shds_column_widths',json.dumps(widths,ensure_ascii=False))
    def refresh_employees(self):
        rows = self.service.list_employees(self.emp_search.text()); self.emp_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate([r["id"], r["fio"], r["personnel_no"], r["department"], r["position"], r["schedule_type"]]): self.emp_table.setItem(i, j, QTableWidgetItem(str(v or "")))
    def refresh_events(self):
        rows = self.service.list_events(self.event_search.text()); self.event_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            batch_id = r["batch_id"] if "batch_id" in r.keys() else None
            for j, v in enumerate([r["id"], r["fio"], ("👥 " if batch_id else "") + r["event_type"], r["subtype"], format_date(r["start_date"]), format_date(r["end_date"]), r["location"], r["basis"]]):
                item = QTableWidgetItem(str(v or ""))
                if j == 0:
                    item.setData(Qt.UserRole, batch_id or "")
                self.event_table.setItem(i, j, item)
    def refresh_summary(self):
        target=self.summary_date.date().toString("yyyy-MM-dd"); all_metrics=self.service.staff_metrics(target); values=[("По штату","staff"),("По списку","listed"),("Вакантно","vacant"),("Отсутствуют","absent"),("На лицо","present")]
        for row,(label,key) in enumerate(values):
            self.summary_table.setItem(row,0,QTableWidgetItem(label))
            self.summary_table.setItem(row,1,QTableWidgetItem(str(all_metrics['total'][key])))
            for col,section in enumerate(SECTIONS,2): self.summary_table.setItem(row,col,QTableWidgetItem(str(all_metrics['by_section'][section][key])))
        active_section=self.summary_section.currentText(); metrics=self.service.staff_metrics(target,active_section); ids=set(metrics['employee_sections']); summary=self.service.daily_summary(target); summary['statuses']=[s for s in summary['statuses'] if s.employee_id in ids]; grouped=defaultdict(list)
        for s in summary['statuses']: grouped[(s.status,s.subtype)].append(s)
        summary['grouped']=grouped; self._last_summary=summary; self.summary_tree.clear()
        unassigned=self.service.unassigned_active_employees(); warning=[]
        if unassigned: warning.append(f"Есть работники, не назначенные на штатные единицы: {len(unassigned)}")
        if not all_metrics['valid']: warning.append("Обнаружено расхождение в расчёте личного состава.")
        self.diagnostic_label.setText("   ".join(warning))
        for status in ["Работа", "Работа / график не задан", "Выходной"]:
            members = summary["grouped"].get((status, ""), []); item = QTreeWidgetItem([status, str(len(members))]); item.setData(0, Qt.UserRole, (status, "")); self.summary_tree.addTopLevelItem(item)
        for parent, subtypes in EVENT_TYPES.items():
            if subtypes:
                count = sum(len(summary["grouped"].get((parent, s), [])) for s in subtypes) + len(summary["grouped"].get((parent, ""), [])); parent_item = QTreeWidgetItem([parent, str(count)]); self.summary_tree.addTopLevelItem(parent_item)
                for subtype in subtypes:
                    members = summary["grouped"].get((parent, subtype), []); item = QTreeWidgetItem([subtype, str(len(members))]); item.setData(0, Qt.UserRole, (parent, subtype)); parent_item.addChild(item)
            else:
                members = summary["grouped"].get((parent, ""), []); item = QTreeWidgetItem([parent, str(len(members))]); item.setData(0, Qt.UserRole, (parent, "")); self.summary_tree.addTopLevelItem(item)
        self.summary_tree.expandAll(); self.summary_people.setRowCount(0)
    def refresh_state(self):
        if not hasattr(self,'state_table'): return
        rows=self.service.staff_state_on_date(self.state_date.date().toString('yyyy-MM-dd')); self.state_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate([row['unit_number'],row['fio'],row['section'],row['group'],row['position'],row['state'],row['reason']]): self.state_table.setItem(i,j,QTableWidgetItem(value))
    def open_metric_people(self,row,col):
        if row not in (3,4) or col==0: return
        section="Все" if col==1 else SECTIONS[col-2]; kind="absent" if row==3 else "present"; people=self.service.staff_people(self.summary_date.date().toString("yyyy-MM-dd"),kind,section)
        dialog=QDialog(self); dialog.setWindowTitle("Отсутствуют" if kind=="absent" else "На лицо"); layout=QVBoxLayout(dialog); table=QTableWidget(len(people),3); table.setHorizontalHeaderLabels(["ФИО","Отделение","Причина отсутствия" if kind=="absent" else "Должность"]); style_table(table)
        for i,p in enumerate(people):
            for j,v in enumerate([p['fio'],p['section'],p['reason'] if kind=='absent' else p['position']]): table.setItem(i,j,QTableWidgetItem(v))
        layout.addWidget(table); close=QPushButton("Закрыть"); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.resize(700,400); dialog.exec()
    def show_group_members(self, item: QTreeWidgetItem):
        key = item.data(0, Qt.UserRole)
        if not key: return
        members = self._last_summary["grouped"].get(tuple(key), []); self.summary_people.setRowCount(len(members))
        for i, person in enumerate(members):
            for j, value in enumerate([person.fio, person.personnel_no, person.position, "событие" if person.source == "event" else ("график" if person.source == "schedule" else "по умолчанию")]): self.summary_people.setItem(i, j, QTableWidgetItem(value))
    def add_employee(self):
        dialog=EmployeeDialog(self.service, parent=self); dialog.exec()
        if dialog.created_in_dialog and dialog.employee_id:
            choice=QMessageBox(self); choice.setWindowTitle("Назначение на штатную единицу"); choice.setText("Назначить нового работника на штатную единицу?")
            vacancy=choice.addButton("Выбрать существующую вакансию",QMessageBox.AcceptRole); create=choice.addButton("Создать новую штатную единицу",QMessageBox.ActionRole); leave=choice.addButton("Пока оставить без штатной единицы",QMessageBox.RejectRole)
            # macOS may size a QMessageBox from the short question text rather
            # than from long custom button captions. Keep all three actions
            # readable under the modern theme instead of clipping their labels.
            choice.setMinimumWidth(720)
            for button, width in ((vacancy, 220), (create, 220), (leave, 240)):
                button.setMinimumWidth(width)
            choice.exec()
            if choice.clickedButton() == vacancy:
                vacancies=[unit for unit in self.service.list_staff_units() if not unit['employee_id']]
                if not vacancies: QMessageBox.information(self,"Вакансии","Свободных штатных единиц нет.")
                else:
                    selector=QDialog(self); selector.setWindowTitle("Выберите вакансию"); form=QFormLayout(selector); combo=QComboBox(); [combo.addItem(f"{unit['unit_number']} — {unit['section']}, {unit['position']}",int(unit['id'])) for unit in vacancies]; form.addRow("Вакантная единица",combo); buttons=russian_dialog_buttons("Назначить"); buttons.accepted.connect(selector.accept); buttons.rejected.connect(selector.reject); form.addRow(buttons)
                    if selector.exec(): StaffUnitDialog(self.service,combo.currentData(),self,employee_id=dialog.employee_id,vacancies_only=True).exec()
            elif choice.clickedButton() == create:
                StaffUnitDialog(self.service,parent=self,employee_id=dialog.employee_id).exec()
            elif choice.clickedButton() == leave:
                QMessageBox.information(self,"Сохранено","Работник сохранён, но не назначен на штатную единицу.")
        self.refresh_all()

    def show_unassigned(self):
        UnassignedEmployeesDialog(self.service, self).exec()
        self.refresh_all()
    def edit_employee(self):
        row = self.emp_table.currentRow()
        if row >= 0: EmployeeDialog(self.service, int(self.emp_table.item(row, 0).text()), self).exec(); self.refresh_all()

    def show_archive(self):
        dialog=QDialog(self); dialog.setWindowTitle("Архив работников"); dialog.resize(900,500); layout=QVBoxLayout(dialog); search=QLineEdit(); search.setPlaceholderText("Поиск по ФИО или табельному номеру"); table=QTableWidget(); table.setColumnCount(8); table.setHorizontalHeaderLabels(["ID","ФИО","Таб. №","Последняя должность","Последнее отделение","Последняя группа","Дата приёма","С какого числа отсутствует"]); table.setColumnHidden(0,True); style_table(table); table.setSortingEnabled(True)
        def refresh():
            rows=self.service.archived_employees(search.text()); table.setSortingEnabled(False); table.setRowCount(len(rows))
            for i,p in enumerate(rows):
                values=[p['id'],p['fio'],p['personnel_no'],p['position'],p['section'],p['group_name'] if 'group_name' in p.keys() else '—',p['employment_date'],p['archive_date']]
                for j,value in enumerate(values): table.setItem(i,j,QTableWidgetItem(str(value or '—')))
            table.setSortingEnabled(True)
        search.textChanged.connect(refresh); table.doubleClicked.connect(lambda: EmployeeDialog(self.service,int(table.item(table.currentRow(),0).text()),dialog).exec()); layout.addWidget(search); layout.addWidget(table); close=QPushButton("Закрыть"); close.clicked.connect(dialog.accept); layout.addWidget(close); refresh(); dialog.exec()
    def add_event(self):
        if EventDialog(self.service, self).exec(): self.refresh_all()
    def _selected_event_row(self) -> tuple[int, str] | None:
        row = self.event_table.currentRow()
        if row < 0: return None
        item = self.event_table.item(row, 0)
        return int(item.text()), (item.data(Qt.UserRole) or "")
    def assign_batch(self, preselected: list[int] | None = None):
        if BatchEventDialog(self.service, self, preselected=preselected).exec(): self.refresh_all()
    def assign_batch_from_staff(self):
        ids: list[int] = []
        selection = self.staff_table.selectionModel()
        for index in selection.selectedRows() if selection else []:
            unit = self.service.staff_unit(int(self.staff_table.item(index.row(), 0).text()))
            if unit and unit["employee_id"]:
                person = self.service.get_employee(int(unit["employee_id"]))
                if person and person["employment_status"] == "Работает":
                    ids.append(int(unit["employee_id"]))
        if not ids:
            QMessageBox.information(self, "Назначить нескольким", "Выделите в ШДС строки с работниками (вакансии не участвуют).")
            return
        self.assign_batch(preselected=ids)
    def open_group(self, batch_id: str):
        if BatchGroupDialog(self.service, batch_id, self).exec(): self.refresh_all()
    def open_selected_group(self):
        selected = self._selected_event_row()
        if not selected: return
        _event_id, batch_id = selected
        if not batch_id:
            QMessageBox.information(self, "Открыть группу", "Это одиночная запись, группы у неё нет."); return
        self.open_group(batch_id)
    def edit_event(self):
        selected = self._selected_event_row()
        if not selected: return
        event_id, batch_id = selected
        if batch_id:
            self.open_group(batch_id); return
        if EventDialog(self.service, self, event_id=event_id).exec(): self.refresh_all()
    def delete_event(self):
        selected = self._selected_event_row()
        if not selected: return
        event_id, batch_id = selected
        if batch_id:
            count = len(self.service.list_batch_events(batch_id))
            choice = QMessageBox.question(self, "Групповое назначение", f"Запись входит в групповое назначение. Удалить всю группу? Будет удалено записей: {count}.")
            if choice == QMessageBox.Yes:
                self.service.delete_batch_events(batch_id); self.refresh_all()
            return
        if QMessageBox.question(self, "Удалить событие", "Удалить выбранную запись?") == QMessageBox.Yes: self.service.delete_event(event_id); self.refresh_all()
    def copy_summary(self): QApplication.clipboard().setText(self.service.render_daily_text(self.summary_date.date().toString("yyyy-MM-dd"))); QMessageBox.information(self, "Готово", "Расход скопирован в буфер обмена.")
    def seed_demo(self):
        try:
            result = self.service.create_demo_data()
            self.refresh_all()
            QMessageBox.information(self, "Демо", f"Добавлены {result['employees']} вымышленных работника, {result['staff_units']} штатные единицы и {result['events']} события.")
        except ValueError as exc: QMessageBox.warning(self, "Демо", str(exc))


def run_app(db_path: Path):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    ThemeManager().apply(app)
    window = MainWindow(db_path)
    window.show()
    return app.exec()
