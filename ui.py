from __future__ import annotations

import sqlite3
import json
from datetime import date
from pathlib import Path
from collections import defaultdict

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPixmap, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QCompleter, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QMenu,
)

from config import APP_NAME, EVENT_TYPES, SCHEDULE_TYPES, SECTIONS
from database import Database
from services import BatchConflictError, PersonnelService, calculate_age, format_age, natural_sort_key


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
    table.verticalHeader().setDefaultSectionSize(30)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)


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
        self.resize(1040, 720)
        self.tabs = QTabWidget(); self.main_tab = QWidget(); self.tabs.addTab(self.main_tab, "Основное")
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
        self.photo = PhotoLabel("ФОТО"); self.photo.setFixedSize(140, 175); self.photo.setAlignment(Qt.AlignCenter); self.photo.setStyleSheet("border: 1px solid #9a9a9a; background: #eeeeee; color: #666;")
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
        self.employment_status.currentTextChanged.connect(self.update_header); self.employment_status.currentTextChanged.connect(self._status_changed)
        self.birth_date.dateChanged.connect(self.update_age)
        forms = QGridLayout(); forms.setColumnStretch(0, 1); forms.setColumnStretch(1, 1)
        self.age_label=QLabel("Не указан"); personal = QGroupBox("Личные данные"); f = QFormLayout(personal); f.addRow("ФИО*", self.fio); f.addRow("Табельный номер*", self.personnel_no); f.addRow("Дата рождения", self.birth_date); f.addRow("Возраст", self.age_label); f.addRow("Дата начала работы", self.employment_date)
        contacts = QGroupBox("Контакты"); f = QFormLayout(contacts); f.addRow("Телефон", self.phone); f.addRow("E-mail", self.email)
        addresses = QGroupBox("Адреса"); f = QFormLayout(addresses); f.addRow("Фактический адрес", self.factual_address); f.addRow("Адрес регистрации", self.registration_address)
        self.group_label = QLineEdit(); self.group_label.setPlaceholderText("Например, 1 группа")
        self.assignment_status = QLabel("Не назначен на штатную единицу"); self.assignment_status.setWordWrap(True)
        service = QGroupBox("Служебные данные"); f = QFormLayout(service); f.addRow("Подразделение", self.department); f.addRow("Отделение", self.section); f.addRow("Группа", self.group_label); f.addRow("Должность", self.position); f.addRow("Статус работника", self.employment_status); f.addRow("С какого числа отсутствует", self.archive_date); f.addRow("Штатное назначение", self.assignment_status)
        self._apply_field_completers()
        schedule = QGroupBox("График работы"); f = QFormLayout(schedule); f.addRow("График", self.schedule_type); f.addRow("Дата рабочей смены", self.schedule_anchor); f.addRow(QLabel("Укажите любую известную рабочую смену. Остальные даты программа рассчитает автоматически."))
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

    def update_header(self) -> None:
        self.header_fio.setText(self.fio.text().strip() or "Новый работник")
        self.header_position.setText(f"Должность: {self.position.text().strip() or 'не указано'}")
        self.header_department.setText(f"Подразделение: {self.department.text().strip() or 'не указано'}")
        self.header_section.setText(f"Отделение: {self.section.currentText()}")
        number = self.personnel_no.text().strip() or "не указан"
        status = self.current_daily_status or (self.employment_status.currentText() if hasattr(self, "employment_status") else "—")
        self.header_meta.setText(f"Табельный №: {number}    •    Статус на сегодня: {status}")

    def _apply_field_completers(self) -> None:
        attach_completer(self.position, self.service.unique_field_values("position"))
        attach_completer(self.department, self.service.unique_field_values("department"))
        attach_completer(self.group_label, self.service.unique_field_values("group_name"))
        section_values = list(dict.fromkeys([*SECTIONS, *self.service.unique_field_values("section")]))
        current = self.section.currentText()
        self.section.blockSignals(True)
        self.section.clear()
        self.section.addItems(section_values)
        self.section.setCurrentText(current)
        self.section.blockSignals(False)
        if self.section.lineEdit() is not None:
            attach_completer(self.section.lineEdit(), section_values)

    def update_age(self, *_args) -> None:
        try:
            birth = iso_from_dateedit(self.birth_date, True)
            self.age_label.setText(format_age(birth))
        except Exception:
            self.age_label.setText("Не указан")

    def _status_changed(self, status: str) -> None:
        if status != "Работает" and self.archive_date.date() == NULL_DATE:
            self.archive_date.setDate(QDate.currentDate())

    def load_employee(self) -> None:
        person = self.service.get_employee(self.employee_id)
        if not person: return
        for key, widget in [("fio", self.fio), ("personnel_no", self.personnel_no), ("effective_department", self.department), ("effective_position", self.position), ("factual_address", self.factual_address), ("registration_address", self.registration_address), ("phone", self.phone), ("email", self.email)]: widget.setText(person[key] or "")
        set_dateedit(self.birth_date, person["birth_date"], True); set_dateedit(self.employment_date, person["employment_date"], True); set_dateedit(self.schedule_anchor, person["schedule_anchor_date"], True); set_dateedit(self.archive_date, person["archive_date"], True)
        schedule = person["schedule_type"] or "Не задан"
        if self.schedule_type.findText(schedule) < 0:
            self.schedule_type.addItem(schedule)
        self.schedule_type.setCurrentText(schedule); self.employment_status.setCurrentText(person["employment_status"] or "Работает"); self.section.setCurrentText(person["effective_section"] or "Не указано"); self.group_label.setText("" if (person["effective_group"] or "—") == "—" else person["effective_group"])
        med, periodic = self.service.latest_check_dates(self.employee_id); self.latest_medical.setText(format_date(med)); self.latest_periodic.setText(format_date(periodic))
        today = date.today().isoformat()
        daily = next((item for item in self.service.daily_statuses(today) if item.employee_id == self.employee_id), None)
        self.current_daily_status = daily.label if daily else person["employment_status"]
        self.update_age()
        assigned = bool(person["staff_unit_id"])
        for widget in (self.department, self.section, self.position, self.group_label):
            widget.setEnabled(not assigned)
            widget.setToolTip("Данные определяются назначенной штатной единицей." if assigned else "")
        self.assignment_status.setText(self.service.assignment_status_text(person))
        self.update_header(); self.refresh_photo(person["photo_path"])
        self._clean_state = self.form_state()

    def form_state(self):
        return (self.fio.text(),self.personnel_no.text(),self.department.text(),self.section.currentText(),self.group_label.text(),self.position.text(),iso_from_dateedit(self.birth_date,True),iso_from_dateedit(self.employment_date,True),self.factual_address.text(),self.registration_address.text(),self.phone.text(),self.email.text(),self.schedule_type.currentText(),iso_from_dateedit(self.schedule_anchor,True),self.employment_status.currentText(),iso_from_dateedit(self.archive_date,True))

    def has_unsaved_changes(self):
        return self._clean_state is not None and self.form_state()!=self._clean_state

    def closeEvent(self, event):
        if not self.has_unsaved_changes():
            event.accept()
            return
        choice=QMessageBox.question(self,"Несохранённые изменения","Есть несохранённые изменения. Сохранить их?",QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        if choice == QMessageBox.Save:
            if self.save(): event.accept()
            else: event.ignore()
        elif choice == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()

    def refresh_photo(self, relative_path: str | None = None) -> None:
        photo_file = self.service.photo_file(relative_path)
        pixmap = QPixmap(str(photo_file)) if photo_file and photo_file.exists() else QPixmap()
        if pixmap.isNull():
            pixmap = QPixmap(self.photo.size()); pixmap.fill(QColor("#eeeeee")); painter = QPainter(pixmap); painter.setPen(QColor("#777777")); painter.drawText(pixmap.rect(), Qt.AlignCenter, "ФОТО\nне добавлено"); painter.end()
        self.photo.setPixmap(pixmap.scaled(self.photo.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)); self.photo_remove.setEnabled(bool(relative_path and photo_file and photo_file.exists()))

    def copy_employee_data(self,index):
        choices={1:self.fio.text().strip(),2:f"{self.fio.text().strip()} ({self.personnel_no.text().strip()})",3:self.phone.text().strip(),4:self.position.text().strip()}
        if index in choices: QApplication.clipboard().setText(choices[index]); self.copy_data.setCurrentIndex(0)

    def choose_photo(self) -> None:
        if not self._require_saved(): return
        path, _ = QFileDialog.getOpenFileName(self, "Выберите фотографию", "", "Изображения (*.jpg *.jpeg *.png *.bmp *.webp)")
        if not path: return
        try:
            self.service.save_photo(self.employee_id, path); self.load_employee(); QMessageBox.information(self, "Фотография", "Фотография сохранена и уменьшена для карточки.")
        except ValueError as exc: QMessageBox.warning(self, "Фотография", str(exc))

    def delete_photo(self) -> None:
        if self._require_saved() and QMessageBox.question(self, "Удалить фото", "Удалить фотографию работника?") == QMessageBox.Yes:
            self.service.remove_photo(self.employee_id); self.load_employee()

    def show_photo(self) -> None:
        if not self.employee_id: return
        person = self.service.get_employee(self.employee_id); photo_file = self.service.photo_file(person["photo_path"] if person else None)
        if not photo_file or not photo_file.exists(): return
        dialog = QDialog(self); dialog.setWindowTitle("Фотография работника"); layout = QVBoxLayout(dialog); label = QLabel(); pixmap = QPixmap(str(photo_file)); label.setPixmap(pixmap.scaled(700, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)); layout.addWidget(label); close = QPushButton("Закрыть"); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def save(self) -> bool:
        if not self.fio.text().strip():
            QMessageBox.warning(self, "Проверка", "Укажите ФИО."); self.fio.setFocus(); return False
        if not self.personnel_no.text().strip():
            QMessageBox.warning(self, "Проверка", "Укажите табельный номер."); self.personnel_no.setFocus(); return False
        data = {"fio": self.fio.text().strip(), "personnel_no": self.personnel_no.text().strip(), "department": self.department.text().strip(), "section": self.section.currentText(), "group_name": self.group_label.text().strip(), "position": self.position.text().strip(), "birth_date": iso_from_dateedit(self.birth_date, True), "employment_date": iso_from_dateedit(self.employment_date, True), "factual_address": self.factual_address.text().strip(), "registration_address": self.registration_address.text().strip(), "phone": self.phone.text().strip(), "email": self.email.text().strip(), "schedule_type": self.schedule_type.currentText(), "schedule_anchor_date": iso_from_dateedit(self.schedule_anchor, True) if self.schedule_type.currentText() == "1/3" else None, "employment_status": self.employment_status.currentText(), "archive_date": iso_from_dateedit(self.archive_date, True)}
        try:
            is_new = self.employee_id is None
            self.employee_id = self.service.save_employee(data, self.employee_id); self.created_in_dialog = self.created_in_dialog or is_new; self.load_employee(); self.refresh_records()
            person = self.service.get_employee(self.employee_id)
            if person and person["employment_status"] == "Работает" and not person["staff_unit_id"]:
                QMessageBox.information(self, "Сохранено", "Работник сохранён, но не назначен на штатную единицу.")
            else:
                QMessageBox.information(self, "Сохранено", "Карточка работника сохранена.")
            return True
        except sqlite3.IntegrityError: QMessageBox.critical(self, "Ошибка", "Работник с таким табельным номером уже существует."); return False

    def _require_saved(self) -> bool:
        if self.employee_id:
            if self.has_unsaved_changes():
                choice=QMessageBox.question(self,"Несохранённые изменения","Сначала сохранить изменения карточки?",QMessageBox.Save|QMessageBox.Cancel,QMessageBox.Save)
                if choice!=QMessageBox.Save: return False
                if not self.save(): return False
            return True
        QMessageBox.information(self, "Сначала сохраните", "Сначала сохраните карточку работника, затем добавляйте записи."); return False

    def _record_id(self, section: str) -> int | None:
        row = self.record_tables[section].currentRow()
        if row >= 0: return int(self.record_tables[section].item(row, 0).text())
        QMessageBox.information(self, "Выберите запись", "Сначала выберите запись в таблице."); return None

    def _open_record_dialog(self, title: str, fields: list[tuple[str, str, bool]], initial: dict | None = None):
        dialog = RecordDialog(title, fields, initial, self); return dialog if dialog.exec() else None

    def add_medical(self):
        if self._require_saved() and (dialog := self._open_record_dialog("Медкомиссия", [("Дата", "check_date", True), ("Примечание", "notes", False)])):
            self.service.add_medical_check(self.employee_id, dialog.values["check_date"], dialog.values["notes"]); self.refresh_records(); self.load_employee()
    def edit_medical(self): self.edit_record("Медкомиссия")
    def delete_medical(self): self.delete_record("Медкомиссия")
    def add_periodic(self):
        if self._require_saved() and (dialog := self._open_record_dialog("Периодическая проверка", [("Дата", "check_date", True), ("Результат", "result", False), ("Примечание", "notes", False)])):
            self.service.add_periodic_check(self.employee_id, dialog.values["check_date"], dialog.values["result"], dialog.values["notes"]); self.refresh_records(); self.load_employee()
    def edit_periodic(self): self.edit_record("Периодическая проверка")
    def delete_periodic(self): self.delete_record("Периодическая проверка")
    def add_training(self):
        fields = [("Дата", "training_date", True), ("Специальность", "specialty", False), ("Приказ", "order_ref", False), ("Удостоверение", "certificate", False), ("Примечание", "notes", False)]
        if self._require_saved() and (dialog := self._open_record_dialog("Обучение", fields)):
            self.service.add_training(self.employee_id, dialog.values["specialty"], dialog.values["training_date"], dialog.values["order_ref"], dialog.values["certificate"], dialog.values["notes"]); self.refresh_records()
    def edit_training(self): self.edit_record("Обучение")
    def delete_training(self): self.delete_record("Обучение")
    def add_weapon(self):
        if self._require_saved() and (dialog := self._open_record_dialog("Оружие", [("Наименование оружия", "weapon_name", False), ("Номер", "serial_number", False)])):
            try: self.service.add_weapon(self.employee_id, dialog.values["weapon_name"], dialog.values["serial_number"]); self.refresh_records()
            except ValueError as exc: QMessageBox.warning(self,"Оружие",str(exc))
    def edit_weapon(self): self.edit_record("Оружие")
    def delete_weapon(self): self.delete_record("Оружие")
    def add_absence(self):
        if self._require_saved() and EventDialog(self.service, self, employee_id=self.employee_id).exec(): self.refresh_records(); self.load_employee()
    def edit_absence(self): self.edit_record("Отсутствия")
    def delete_absence(self): self.delete_record("Отсутствия")

    def edit_record(self, section: str) -> None:
        if not self._require_saved() or (record_id := self._record_id(section)) is None: return
        if section == "Отсутствия":
            event = self.service.get_event(record_id)
            if event and event["batch_id"]:
                # Часть группы отдельно не редактируется — открываем всю группу.
                if BatchGroupDialog(self.service, event["batch_id"], self).exec(): self.refresh_records(); self.load_employee()
                return
            if EventDialog(self.service, self, employee_id=self.employee_id, event_id=record_id).exec(): self.refresh_records(); self.load_employee()
            return
        table = {"Медкомиссия": "medical_checks", "Периодическая проверка": "periodic_checks", "Обучение": "trainings", "Оружие": "weapons"}[section]; record = self.service.get_history_record(table, record_id, self.employee_id)
        if not record: return
        fields = {"Медкомиссия": [("Дата", "check_date", True), ("Примечание", "notes", False)], "Периодическая проверка": [("Дата", "check_date", True), ("Результат", "result", False), ("Примечание", "notes", False)], "Обучение": [("Дата", "training_date", True), ("Специальность", "specialty", False), ("Приказ", "order_ref", False), ("Удостоверение", "certificate", False), ("Примечание", "notes", False)], "Оружие": [("Наименование оружия", "weapon_name", False), ("Номер", "serial_number", False)]}[section]
        values = dict(record); values["weapon_name"] = ((record["weapon_type"] or "") + (f" {record['model']}" if record["model"] else "")).strip()
        if dialog := self._open_record_dialog(section, fields, values):
            try: self.service.update_history_record(table, record_id, self.employee_id, dialog.values); self.refresh_records(); self.load_employee()
            except ValueError as exc: QMessageBox.warning(self,"Оружие",str(exc))

    def delete_record(self, section: str) -> None:
        if not self._require_saved() or (record_id := self._record_id(section)) is None: return
        if QMessageBox.question(self, "Удалить запись", "Удалить выбранную запись?") != QMessageBox.Yes: return
        if section == "Отсутствия":
            event = self.service.get_event(record_id)
            if event and event["batch_id"]:
                # Удалить можно только всю группу целиком.
                if QMessageBox.question(self, "Групповое назначение", "Запись входит в групповое назначение. Отдельно удалить её нельзя. Открыть группу?") == QMessageBox.Yes:
                    if BatchGroupDialog(self.service, event["batch_id"], self).exec(): self.refresh_records(); self.load_employee()
                return
            self.service.delete_event(record_id)
        else: self.service.delete_history_record({"Медкомиссия": "medical_checks", "Периодическая проверка": "periodic_checks", "Обучение": "trainings", "Оружие": "weapons"}[section], record_id, self.employee_id)
        self.refresh_records(); self.load_employee()

    def refresh_records(self) -> None:
        if not self.employee_id: return
        records = {"Медкомиссия": [(r["id"], format_date(r["check_date"]), r["notes"]) for r in self.service.list_simple_history("medical_checks", self.employee_id)], "Периодическая проверка": [(r["id"], format_date(r["check_date"]), r["result"], r["notes"]) for r in self.service.list_simple_history("periodic_checks", self.employee_id)], "Обучение": [(r["id"], format_date(r["training_date"]), r["specialty"], r["order_ref"], r["certificate"], r["notes"]) for r in self.service.list_simple_history("trainings", self.employee_id)], "Оружие": [(r["id"], ((r["weapon_type"] or "") + (f" {r['model']}" if r["model"] else "")).strip(), r["serial_number"]) for r in self.service.list_simple_history("weapons", self.employee_id)], "Отсутствия": [(r["id"], r["event_type"], r["subtype"], format_date(r["start_date"]), format_date(r["end_date"]), r["location"], r["basis"], r["notes"]) for r in self.service.events_for_employee(self.employee_id)]}
        for section, rows in records.items():
            table = self.record_tables[section]; table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                for column, value in enumerate(row): table.setItem(row_index, column, QTableWidgetItem(str(value or "")))


class RecordDialog(QDialog):
    def __init__(self, title: str, fields: list[tuple[str, str, bool]], initial: dict | None = None, parent=None):
        super().__init__(parent); self.setWindowTitle(title); self.values: dict[str, str] = {}; layout = QFormLayout(self); self.widgets: dict[str, QWidget] = {}; initial = initial or {}
        for label, key, is_date in fields:
            widget = new_date_edit() if is_date else QLineEdit(str(initial.get(key) or ""))
            if is_date: set_dateedit(widget, initial.get(key))
            self.widgets[key] = widget; layout.addRow(label, widget)
        buttons = russian_dialog_buttons(); buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)
    def _accept(self):
        self.values = {key: (widget.date().toString("yyyy-MM-dd") if isinstance(widget, QDateEdit) else widget.text().strip()) for key, widget in self.widgets.items()}; self.accept()


class EventDialog(QDialog):
    def __init__(self, service: PersonnelService, parent=None, employee_id: int | None = None, event_id: int | None = None):
        super().__init__(parent); self.service, self.employee_id, self.event_id = service, employee_id, event_id; self.setWindowTitle("Изменить событие" if event_id else "Добавить событие"); self.resize(560, 430); form = QFormLayout(self)
        self.employee = QComboBox(); [self.employee.addItem(f"{p['fio']} ({p['personnel_no']})", int(p["id"])) for p in service.list_employees()]; self.event_type = QComboBox(); self.event_type.addItems(EVENT_TYPES.keys()); self.event_type.currentTextChanged.connect(self.update_subtypes); self.subtype = QComboBox(); self.start, self.end = new_date_edit(), new_date_edit(); self.location, self.basis = QLineEdit(), QLineEdit(); self.notes = QTextEdit(); self.notes.setFixedHeight(80)
        for label, field in [("Работник", self.employee), ("Категория", self.event_type), ("Подтип", self.subtype), ("С", self.start), ("По", self.end), ("Место / объект", self.location), ("Основание", self.basis), ("Примечание", self.notes)]: form.addRow(label, field)
        buttons = russian_dialog_buttons(); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); form.addRow(buttons); self.update_subtypes(self.event_type.currentText())
        if employee_id is not None:
            index = self.employee.findData(employee_id); self.employee.setCurrentIndex(index); self.employee.setEnabled(False)
        if event_id is not None:
            event = service.get_event(event_id)
            if event:
                self.employee.setCurrentIndex(self.employee.findData(int(event["employee_id"]))); self.employee.setEnabled(False); self.event_type.setCurrentText(event["event_type"]); self.update_subtypes(event["event_type"]); self.subtype.setCurrentText(event["subtype"]); set_dateedit(self.start, event["start_date"]); set_dateedit(self.end, event["end_date"]); self.location.setText(event["location"]); self.basis.setText(event["basis"]); self.notes.setPlainText(event["notes"])
    def update_subtypes(self, event_type: str): self.subtype.clear(); self.subtype.addItems(EVENT_TYPES.get(event_type, [])); self.subtype.setEnabled(bool(EVENT_TYPES.get(event_type)))
    def save(self):
        if self.employee.currentData() is None: QMessageBox.warning(self, "Нет работников", "Сначала добавьте хотя бы одного работника."); return
        data = {"employee_id": str(self.employee.currentData()), "event_type": self.event_type.currentText(), "subtype": self.subtype.currentText() if self.subtype.isEnabled() else "", "start_date": self.start.date().toString("yyyy-MM-dd"), "end_date": self.end.date().toString("yyyy-MM-dd"), "location": self.location.text().strip(), "basis": self.basis.text().strip(), "notes": self.notes.toPlainText().strip()}
        try:
            self.service.update_event(self.event_id, int(self.employee.currentData()), data) if self.event_id else self.service.add_event(data); self.accept()
        except ValueError as exc: QMessageBox.warning(self, "Нельзя сохранить", str(exc))


class BatchEventDialog(QDialog):
    """Групповое назначение одного события нескольким работникам (v0.5, этап 1).

    Создаёт обычные одиночные записи с общим batch_id.  В режиме редактирования
    (batch_id задан) меняет только параметры события — состав группы неизменен."""
    def __init__(self, service: PersonnelService, parent=None, preselected: list[int] | None = None, batch_id: str | None = None):
        super().__init__(parent)
        self.service, self.batch_id = service, batch_id
        self.selected: set[int] = {int(value) for value in (preselected or [])}
        editing = batch_id is not None
        self.setWindowTitle("Изменить группу" if editing else "Назначить нескольким")
        self.resize(880, 640)
        root = QVBoxLayout(self)

        people_box = QGroupBox("Работники")
        people = QVBoxLayout(people_box)
        controls = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Поиск по ФИО...")
        self.section_filter = QComboBox(); self.section_filter.addItems(["Все", *SECTIONS])
        self.counter = QLabel()
        controls.addWidget(QLabel("Поиск:")); controls.addWidget(self.search, 1)
        controls.addWidget(QLabel("Отделение:")); controls.addWidget(self.section_filter)
        controls.addWidget(self.counter); people.addLayout(controls)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["✓", "ФИО", "Должность", "Отделение", "Подразделение"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        people.addWidget(self.table)
        root.addWidget(people_box, 1)

        event_box = QGroupBox("Параметры события")
        form = QFormLayout(event_box)
        self.event_type = QComboBox(); self.event_type.addItems(EVENT_TYPES.keys())
        self.event_type.currentTextChanged.connect(self.update_subtypes)
        self.subtype = QComboBox()
        self.start, self.end = new_date_edit(), new_date_edit()
        self.location, self.basis = QLineEdit(), QLineEdit()
        self.notes = QTextEdit(); self.notes.setFixedHeight(60)
        for label, field in [("Категория", self.event_type), ("Подтип", self.subtype), ("С", self.start), ("По", self.end), ("Место / объект", self.location), ("Основание", self.basis), ("Примечание", self.notes)]:
            form.addRow(label, field)
        root.addWidget(event_box)

        buttons = russian_dialog_buttons("Сохранить")
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.search.textChanged.connect(self.rebuild_table)
        self.section_filter.currentTextChanged.connect(self.rebuild_table)
        self.table.itemChanged.connect(self._item_changed)
        self._people = []
        for person in service.list_employees():
            details = service.get_employee(int(person["id"])) or person
            self._people.append((int(person["id"]), person["fio"], details["effective_position"] or "—", details["effective_section"] or "—", details["effective_department"] or "—"))
        if editing:
            events = service.list_batch_events(batch_id)
            self.selected = {int(event["employee_id"]) for event in events}
            for widget in (self.search, self.section_filter, self.table):
                widget.setEnabled(False)
            if events:
                first = events[0]
                self.event_type.setCurrentText(first["event_type"]); self.update_subtypes(first["event_type"])
                self.subtype.setCurrentText(first["subtype"])
                set_dateedit(self.start, first["start_date"]); set_dateedit(self.end, first["end_date"])
                self.location.setText(first["location"]); self.basis.setText(first["basis"]); self.notes.setPlainText(first["notes"])
        self.update_subtypes(self.event_type.currentText())
        self.rebuild_table()

    def update_subtypes(self, event_type: str):
        self.subtype.clear(); self.subtype.addItems(EVENT_TYPES.get(event_type, [])); self.subtype.setEnabled(bool(EVENT_TYPES.get(event_type)))

    def rebuild_table(self) -> None:
        needle = self.search.text().strip().casefold()
        section = self.section_filter.currentText()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for employee_id, fio, position, emp_section, department in self._people:
            if needle and needle not in fio.casefold():
                continue
            if section != "Все" and emp_section != section:
                continue
            row = self.table.rowCount(); self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if employee_id in self.selected else Qt.Unchecked)
            check.setData(Qt.UserRole, employee_id)
            self.table.setItem(row, 0, check)
            for column, value in enumerate((fio, position, emp_section, department), 1):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.blockSignals(False)
        self._update_counter()

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        employee_id = item.data(Qt.UserRole)
        if employee_id is None:
            return
        if item.checkState() == Qt.Checked:
            self.selected.add(int(employee_id))
        else:
            self.selected.discard(int(employee_id))
        self._update_counter()

    def _update_counter(self) -> None:
        self.counter.setText(f"Выбрано: {len(self.selected)}")

    def _event_data(self) -> dict:
        return {
            "event_type": self.event_type.currentText(),
            "subtype": self.subtype.currentText() if self.subtype.isEnabled() else "",
            "start_date": self.start.date().toString("yyyy-MM-dd"),
            "end_date": self.end.date().toString("yyyy-MM-dd"),
            "location": self.location.text().strip(),
            "basis": self.basis.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }

    def show_conflicts(self, conflicts: list[dict]) -> None:
        lines = []
        for item in conflicts:
            label = item["event_type"] + (f" / {item['subtype']}" if item["subtype"] else "")
            line = f"• {item['fio']}: {label}, {format_date(item['start_date'])} — {format_date(item['end_date'])}"
            if item.get("notes"):
                line += f" ({item['notes']})"
            lines.append(line)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Конфликт периодов")
        box.setText("Группа не создана: у части работников есть пересечения с существующими событиями.\nНи одна запись не создана. Измените список работников или период.")
        box.setDetailedText("\n".join(lines))
        box.exec()

    def save(self):
        data = self._event_data()
        try:
            if self.batch_id:
                self.service.update_batch_events(self.batch_id, data)
            else:
                ids = sorted(self.selected)
                if len(ids) < 2:
                    QMessageBox.warning(self, "Групповое назначение", "Выберите не менее двух работников. Одиночное назначение выполняется кнопкой «Добавить».")
                    return
                self.service.create_batch_events(ids, data)
            self.accept()
        except BatchConflictError as exc:
            self.show_conflicts(exc.conflicts)
        except ValueError as exc:
            QMessageBox.warning(self, "Нельзя сохранить", str(exc))


class BatchGroupDialog(QDialog):
    """Просмотр группового назначения и действия над всей группой."""
    def __init__(self, service: PersonnelService, batch_id: str, parent=None):
        super().__init__(parent)
        self.service, self.batch_id = service, batch_id
        self.setWindowTitle("Групповое назначение")
        self.resize(760, 480)
        root = QVBoxLayout(self)
        self.header = QLabel(); self.header.setStyleSheet("font-size:14px;font-weight:600;")
        self.header.setWordWrap(True)
        root.addWidget(self.header)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ФИО", "Должность", "Отделение", "Таб. №"])
        style_table(self.table)
        root.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        edit = QPushButton("Изменить группу"); edit.clicked.connect(self.edit_group)
        delete = QPushButton("Удалить группу"); delete.clicked.connect(self.delete_group)
        close = QPushButton("Закрыть"); close.clicked.connect(self.reject)
        buttons.addWidget(edit); buttons.addWidget(delete); buttons.addStretch(); buttons.addWidget(close)
        root.addLayout(buttons)
        self.reload()

    def reload(self) -> None:
        events = self.service.list_batch_events(self.batch_id)
        if not events:
            self.reject(); return
        first = events[0]
        label = first["event_type"] + (f" / {first['subtype']}" if first["subtype"] else "")
        period = f"{format_date(first['start_date'])} — {format_date(first['end_date'])}"
        comment = first["notes"] or "—"
        self.header.setText(f"{label}    •    {period}    •    Работников: {len(events)}\nПримечание: {comment}")
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            for column, value in enumerate((event["fio"], event["position"] or "—", event["section"] or "—", event["personnel_no"])):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def edit_group(self):
        if BatchEventDialog(self.service, self, batch_id=self.batch_id).exec():
            self.reload()

    def delete_group(self):
        count = len(self.service.list_batch_events(self.batch_id))
        if QMessageBox.question(self, "Удалить группу", f"Удалить всю группу? Будет удалено записей: {count}.") != QMessageBox.Yes:
            return
        self.service.delete_batch_events(self.batch_id)
        self.accept()


class StaffUnitDialog(QDialog):
    def __init__(self, service, unit_id=None, parent=None, employee_id: int | None = None, vacancies_only: bool = False):
        super().__init__(parent); self.service=service; self.unit_id=unit_id; self.setWindowTitle("Штатная единица"); form=QFormLayout(self)
        self.number=QLineEdit(); self.department=QLineEdit(); self.section=QComboBox(); self.section.addItems(SECTIONS); self.group=QComboBox(); self.group.addItems(["—","1 группа","2 группа","3 группа","4 группа"]); self.position=QLineEdit(); self.employee=QComboBox(); self.employee.addItem("ВАКАНСИЯ", None)
        for p in service.list_employees(include_archived=False):
            if not vacancies_only or p["id"] == employee_id:
                self.employee.addItem(f"{p['fio']} ({p['personnel_no']})",int(p['id']))
        for label,w in [("Номер штатной единицы*",self.number),("Подразделение",self.department),("Отделение*",self.section),("Группа",self.group),("Должность*",self.position),("Работник",self.employee)]: form.addRow(label,w)
        if unit_id:
            u=service.staff_unit(unit_id); self.number.setText(u['unit_number']); self.department.setText(u['department']); self.section.setCurrentText(u['section']); self.group.setCurrentText(u['group_name'] or '—'); self.position.setText(u['position']); self.employee.setCurrentIndex(self.employee.findData(employee_id if employee_id is not None else u['employee_id']))
        elif employee_id is not None:
            self.employee.setCurrentIndex(self.employee.findData(employee_id))
        b=russian_dialog_buttons(); b.accepted.connect(self.save); b.rejected.connect(self.reject); form.addRow(b)
        self.section.currentTextChanged.connect(self._update_group); self._update_group(self.section.currentText())
    def _update_group(self, section):
        grouped = section in {"1 отделение", "2 отделение"}
        self.group.setEnabled(grouped)
        if not grouped: self.group.setCurrentText('—')
    def save(self):
        try:
            self.service.save_staff_unit({'unit_number':self.number.text(),'department':self.department.text(),'section':self.section.currentText(),'group_name':'' if self.group.currentText()=='—' else self.group.currentText(),'position':self.position.text(),'employee_id':self.employee.currentData()},self.unit_id); self.accept()
        except (ValueError,sqlite3.IntegrityError) as e: QMessageBox.warning(self,"Штатная единица",str(e) or "Номер штатной единицы должен быть уникальным.")


class UnassignedEmployeesDialog(QDialog):
    def __init__(self, service: PersonnelService, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Не назначены на штатную единицу")
        self.resize(920, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Действующие работники, которые не занимают штатную единицу."))
        actions = QHBoxLayout()
        open_card = QPushButton("Открыть карточку"); open_card.clicked.connect(self.open_card)
        assign = QPushButton("Назначить на штатную единицу"); assign.clicked.connect(self.assign_to_unit)
        actions.addWidget(open_card); actions.addWidget(assign); actions.addStretch()
        layout.addLayout(actions)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "ФИО", "Таб. №", "Должность", "Отдел", "Отделение"])
        self.table.setColumnHidden(0, True)
        style_table(self.table)
        self.table.doubleClicked.connect(self.open_card)
        layout.addWidget(self.table)
        close = QPushButton("Закрыть"); close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.reload()

    def _selected_employee_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Выберите работника", "Сначала выберите работника в списке.")
            return None
        return int(self.table.item(row, 0).text())

    def reload(self) -> None:
        rows = self.service.unassigned_active_employees()
        self.table.setRowCount(len(rows))
        for index, person in enumerate(rows):
            values = [person["id"], person["fio"], person["personnel_no"], person["position"] or "—", person["department"] or "—", person["section"] or "Не указано"]
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(str(value)))

    def open_card(self) -> None:
        employee_id = self._selected_employee_id()
        if not employee_id:
            return
        EmployeeDialog(self.service, employee_id, self).exec()
        self.reload()

    def assign_to_unit(self) -> None:
        employee_id = self._selected_employee_id()
        if not employee_id:
            return
        vacancies = self.service.vacant_staff_units()
        if not vacancies:
            QMessageBox.information(self, "Вакансии", "Свободных штатных единиц нет.")
            return
        selector = QDialog(self)
        selector.setWindowTitle("Назначить на штатную единицу")
        form = QFormLayout(selector)
        combo = QComboBox()
        for unit in vacancies:
            combo.addItem(
                f"№ {unit['unit_number']} — {unit['department'] or '—'}, {unit['section'] or '—'}, {unit['group_name'] or '—'}, {unit['position'] or '—'}",
                int(unit["id"]),
            )
        form.addRow("Свободная штатная единица", combo)
        buttons = russian_dialog_buttons("Назначить")
        buttons.accepted.connect(selector.accept)
        buttons.rejected.connect(selector.reject)
        form.addRow(buttons)
        if not selector.exec():
            return
        try:
            self.service.assign_employee_to_unit(employee_id, combo.currentData())
        except ValueError as exc:
            QMessageBox.warning(self, "Назначение", str(exc))
            return
        self.reload()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_all"):
            parent.refresh_all()


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path):
        super().__init__(); self.db = Database(db_path); self.service = PersonnelService(self.db); self.setWindowTitle(APP_NAME + " — версия 0.5"); self.resize(1280, 760); self.tabs = QTabWidget(); self.setCentralWidget(self.tabs); self._build_staff_tab(); self._build_events_tab(); self._build_summary_tab(); self._build_menu(); self.refresh_all()
    def _build_menu(self):
        menu = self.menuBar().addMenu("Сервис"); demo = QAction("Добавить демо-данные", self); demo.triggered.connect(self.seed_demo); menu.addAction(demo); dbinfo = QAction("Показать путь к данным", self); dbinfo.triggered.connect(lambda: QMessageBox.information(self, "Данные", f"База: {self.db.path}\nФотографии: {self.db.photos_dir}")); menu.addAction(dbinfo)
    def _build_employees_tab(self):
        tab = QWidget(); root = QVBoxLayout(tab); top = QHBoxLayout(); self.emp_search = QLineEdit(); self.emp_search.setPlaceholderText("Фамилия, табельный номер, подразделение, должность..."); self.emp_search.textChanged.connect(self.refresh_employees); add = QPushButton("Добавить работника"); add.clicked.connect(self.add_employee); edit = QPushButton("Открыть карточку"); edit.clicked.connect(self.edit_employee); top.addWidget(QLabel("Поиск:")); top.addWidget(self.emp_search, 1); top.addWidget(add); top.addWidget(edit); root.addLayout(top); self.emp_table = QTableWidget(0, 6); self.emp_table.setHorizontalHeaderLabels(["ID", "ФИО", "Таб. №", "Подразделение", "Должность", "График"]); self.emp_table.setColumnHidden(0, True); style_table(self.emp_table); self.emp_table.doubleClicked.connect(self.edit_employee); root.addWidget(self.emp_table); self.tabs.addTab(tab, "Личный состав")
    def _build_staff_tab(self):
        tab=QWidget(); root=QVBoxLayout(tab); top=QHBoxLayout(); self.staff_section=QComboBox(); self.staff_section.addItems(["Все",*SECTIONS]); self.staff_section.currentTextChanged.connect(self.refresh_staff); self.staff_search=QLineEdit(); self.staff_search.setPlaceholderText("ФИО, табельный номер, должность, телефон или № штатной единицы..."); self.staff_search.textChanged.connect(self.refresh_staff)
        add_employee=QPushButton("Добавить работника"); add_employee.clicked.connect(self.add_employee); add=QPushButton("Добавить штатную единицу"); add.clicked.connect(self.add_staff); edit=QPushButton("Изменить"); edit.clicked.connect(self.edit_staff); delete=QPushButton("Удалить единицу"); delete.clicked.connect(self.delete_staff); archive=QPushButton("Архив работников"); archive.clicked.connect(self.show_archive); unassigned=QPushButton("Не назначены на штатную единицу"); unassigned.clicked.connect(self.show_unassigned); batch=QPushButton("Назначить нескольким"); batch.clicked.connect(self.assign_batch_from_staff); columns=QPushButton("Колонки ▼"); columns.clicked.connect(self.show_column_menu); reset=QPushButton("Сбросить фильтры"); reset.clicked.connect(self.reset_staff_filters)
        top.addWidget(QLabel("Отделение:")); top.addWidget(self.staff_section); top.addWidget(QLabel("Поиск:")); top.addWidget(self.staff_search,1); [top.addWidget(button) for button in (add_employee,add,edit,delete,archive,unassigned,batch,columns,reset)]; root.addLayout(top)
        self.staff_metrics_label=QLabel(); self.staff_metrics_label.setStyleSheet("font-size:16px;font-weight:600;padding:8px;"); root.addWidget(self.staff_metrics_label)
        self.staff_headers=["ID","№","Отдел","Отделение","Группа","Должность","ФИО","Таб. №","Дата рождения","Возраст","Телефон","Вооружение","Email","Дата приёма","Последняя МК","Последняя ПП","График"]
        self.staff_filters: dict[str, set[str]] = {}; self.staff_table=SpreadsheetTable(0,len(self.staff_headers)); self.staff_table.setHorizontalHeaderLabels(self.staff_headers); self.staff_table.setColumnHidden(0,True); style_table(self.staff_table); self.staff_table.setSelectionMode(QTableWidget.ExtendedSelection); header=self.staff_table.horizontalHeader(); header.setSectionResizeMode(QHeaderView.Interactive); header.setSortIndicatorShown(True); header.sectionClicked.connect(self.sort_staff_by_column); header.setContextMenuPolicy(Qt.CustomContextMenu); header.customContextMenuRequested.connect(self.open_staff_filter_menu); header.sectionResized.connect(self.save_staff_layout); self.staff_table.doubleClicked.connect(self.open_staff_row); self._restore_staff_layout(); root.addWidget(self.staff_table); self.tabs.addTab(tab,"ШДС")
    def _build_events_tab(self):
        tab = QWidget(); root = QVBoxLayout(tab); top = QHBoxLayout(); self.event_search = QLineEdit(); self.event_search.setPlaceholderText("Поиск по работнику или событию..."); self.event_search.textChanged.connect(self.refresh_events); add = QPushButton("Добавить"); add.clicked.connect(self.add_event); batch = QPushButton("Назначить нескольким"); batch.clicked.connect(self.assign_batch); edit = QPushButton("Изменить"); edit.clicked.connect(self.edit_event); group = QPushButton("Открыть группу"); group.clicked.connect(self.open_selected_group); delete = QPushButton("Удалить"); delete.clicked.connect(self.delete_event); top.addWidget(QLabel("Поиск:")); top.addWidget(self.event_search, 1); top.addWidget(add); top.addWidget(batch); top.addWidget(edit); top.addWidget(group); top.addWidget(delete); root.addLayout(top); self.event_table = QTableWidget(0, 8); self.event_table.setHorizontalHeaderLabels(["ID", "Работник", "Категория", "Подтип", "С", "По", "Место", "Основание"]); self.event_table.setColumnHidden(0, True); style_table(self.event_table); self.event_table.doubleClicked.connect(self.edit_event); root.addWidget(self.event_table); self.tabs.addTab(tab, "Занятость и отсутствия")
    def _build_summary_tab(self):
        tab=QWidget(); root=QVBoxLayout(tab); views=QTabWidget(); root.addWidget(views)
        summary_tab=QWidget(); summary_root=QVBoxLayout(summary_tab); top=QHBoxLayout(); self.summary_date=new_date_edit(); self.summary_date.setDate(QDate.currentDate()); self.summary_date.dateChanged.connect(self.refresh_summary); self.summary_section=QComboBox(); self.summary_section.addItems(["Все",*SECTIONS[:-1]]); self.summary_section.currentTextChanged.connect(self.refresh_summary); refresh=QPushButton("Пересчитать"); refresh.clicked.connect(self.refresh_summary); copy=QPushButton("Копировать расход"); copy.clicked.connect(self.copy_summary); top.addWidget(QLabel("Дата расхода:")); top.addWidget(self.summary_date); top.addWidget(QLabel("Подробный расход:")); top.addWidget(self.summary_section); top.addWidget(refresh); top.addStretch(); top.addWidget(copy); summary_root.addLayout(top)
        self.summary_table=QTableWidget(5,6); self.summary_table.setHorizontalHeaderLabels(["Показатель","Всего","Руководство","1 отделение","2 отделение","Не указано"]); self.summary_table.setVerticalHeaderLabels([]); style_table(self.summary_table); self.summary_table.cellClicked.connect(self.open_metric_people); summary_root.addWidget(self.summary_table)
        self.diagnostic_label=QLabel(); self.diagnostic_label.setStyleSheet("color:#9b2c2c;font-weight:600;"); summary_root.addWidget(self.diagnostic_label)
        splitter=QHBoxLayout(); self.summary_tree=QTreeWidget(); self.summary_tree.setHeaderLabels(["Категория","Количество"]); self.summary_tree.itemClicked.connect(self.show_group_members); self.summary_people=QTableWidget(0,4); self.summary_people.setHorizontalHeaderLabels(["ФИО","Таб. №","Должность","Источник"]); style_table(self.summary_people); splitter.addWidget(self.summary_tree,1); splitter.addWidget(self.summary_people,2); summary_root.addLayout(splitter,1); views.addTab(summary_tab,"Сводка")
        state_tab=QWidget(); state_root=QVBoxLayout(state_tab); state_top=QHBoxLayout(); self.state_date=new_date_edit(); self.state_date.setDate(QDate.currentDate()); self.state_date.dateChanged.connect(self.refresh_state); state_top.addWidget(QLabel("Дата:")); state_top.addWidget(self.state_date); state_refresh=QPushButton("Показать"); state_refresh.clicked.connect(self.refresh_state); state_top.addWidget(state_refresh); state_top.addStretch(); state_root.addLayout(state_top); self.state_table=QTableWidget(0,7); self.state_table.setHorizontalHeaderLabels(["№","ФИО","Отделение","Группа","Должность","Состояние","Причина / мероприятие"]); style_table(self.state_table); state_root.addWidget(self.state_table); views.addTab(state_tab,"Состояние на дату"); self.tabs.addTab(tab,"Расход")
    def refresh_all(self): self.refresh_staff(); self.refresh_events(); self.refresh_summary(); self.refresh_state()
    def refresh_staff(self):
        if not hasattr(self,'staff_table'): return
        rows=self.service.list_staff_units(self.staff_section.currentText(),self.staff_search.text(),self.staff_filters); self.staff_table.setRowCount(len(rows))
        for i,u in enumerate(rows):
            employee=self.service.get_employee(int(u['employee_id'])) if u['employee_id'] and u['employment_status']=='Работает' else None; birth=employee['birth_date'] if employee else None; age=calculate_age(birth) if birth else None
            med, periodic = self.service.latest_check_dates(int(u['employee_id'])) if employee else (None, None)
            values=[u['id'],u['unit_number'],u['department'] or '—',u['section'] or 'Не указано',u['group_name'] or '—',u['position'],employee['fio'] if employee else 'ВАКАНСИЯ',(employee['personnel_no'] if employee else '') or '—',birth or '—',str(age) if age is not None else '—',(employee['phone'] if employee else '') or '—',self.service.weapon_summary(int(u['employee_id'])) if employee else '—',(employee['email'] if employee else '') or '—',(employee['employment_date'] if employee else '') or '—',med or '—',periodic or '—',(employee['schedule_type'] if employee else '') or '—']
            keys=[(0,int(u['id'])),(1,natural_sort_key(u['unit_number'])),None,None,None,None,None,(1,natural_sort_key(employee['personnel_no'])) if employee else (2,),(0,birth) if birth else (2,),(0,age) if age is not None else (2,),None,None,None,(0,employee['employment_date']) if employee and employee['employment_date'] else (2,),(0,med) if med else (2,),(0,periodic) if periodic else (2,),None]
            for j,v in enumerate(values):
                item=QTableWidgetItem(str(v or ''))
                if keys[j] is not None: item.setData(Qt.UserRole,keys[j])
                if not employee: item.setBackground(QColor('#fff4d6'))
                if j == 3 and u['section'] == 'Не указано': item.setBackground(QColor('#ffe1e1'))
                self.staff_table.setItem(i,j,item)
        self._apply_staff_sort(); self._update_staff_header_markers()
        metrics_all=self.service.staff_metrics(date.today().isoformat())['total']; undistributed=self.service.staff_metrics(date.today().isoformat(),"Не указано")['total']['staff']; text=f"ПО ШТАТУ: {metrics_all['staff']}     ПО СПИСКУ: {metrics_all['listed']}     ВАКАНСИИ: {metrics_all['vacant']}     ПОКАЗАНО: {len(rows)}"; self.staff_metrics_label.setText(text + (f"     НЕ РАСПРЕДЕЛЕНО: {undistributed}" if undistributed else ""))
    def _update_staff_header_markers(self):
        labels=[header + (" ▼" if header in self.staff_filters and self.staff_filters[header] else "") for header in self.staff_headers]
        self.staff_table.setHorizontalHeaderLabels(labels)
    def open_staff_filter_menu(self, position):
        index=self.staff_table.horizontalHeader().logicalIndexAt(position)
        if index>=0: self.open_staff_filter(index)
    def _staff_sort_key(self, item: QTableWidgetItem | None):
        key = item.data(Qt.UserRole) if item else None
        if isinstance(key, tuple): return (0, key)
        return (1, item.text().casefold() if item else "")
    def sort_staff_by_column(self, column: int):
        if getattr(self, '_staff_sort_column', None) == column and self._staff_sort_order == Qt.AscendingOrder:
            self._staff_sort_order = Qt.DescendingOrder
        else:
            self._staff_sort_column, self._staff_sort_order = column, Qt.AscendingOrder
        self._apply_staff_sort()
    def _apply_staff_sort(self):
        column = getattr(self, '_staff_sort_column', None)
        if column is None: return
        table = self.staff_table
        rows = [[table.takeItem(r, c) for c in range(table.columnCount())] for r in range(table.rowCount())]
        table.setRowCount(0)
        rows.sort(key=lambda items: self._staff_sort_key(items[column]), reverse=self._staff_sort_order == Qt.DescendingOrder)
        table.setRowCount(len(rows))
        for r, items in enumerate(rows):
            for c, item in enumerate(items): table.setItem(r, c, item)
        table.horizontalHeader().setSortIndicator(column, self._staff_sort_order)
    def add_staff(self):
        if StaffUnitDialog(self.service,parent=self).exec(): self.refresh_all()
    def edit_staff(self):
        row=self.staff_table.currentRow()
        if row<0: return
        unit_id=int(self.staff_table.item(row,0).text())
        if StaffUnitDialog(self.service,unit_id,self).exec(): self.refresh_all()

    def delete_staff(self):
        row=self.staff_table.currentRow()
        if row < 0: return
        unit_id=int(self.staff_table.item(row,0).text())
        if QMessageBox.question(self,"Удалить штатную единицу","Удалить выбранную вакантную штатную единицу?") != QMessageBox.Yes: return
        try:
            self.service.delete_staff_unit(unit_id); self.refresh_all()
        except ValueError as exc:
            QMessageBox.warning(self,"Штатная единица",str(exc))
    def open_staff_row(self):
        row=self.staff_table.currentRow()
        if row<0:return
        unit=self.service.staff_unit(int(self.staff_table.item(row,0).text()))
        if self.staff_table.currentColumn() == self.staff_headers.index("Вооружение") and unit['employee_id']:
            self.show_weapons(int(unit['employee_id'])); return
        if unit['employee_id']: EmployeeDialog(self.service,int(unit['employee_id']),self).exec()
        else: StaffUnitDialog(self.service,int(unit['id']),self).exec()
        self.refresh_all()

    def show_weapons(self, employee_id: int):
        person=self.service.get_employee(employee_id); dialog=QDialog(self); dialog.setWindowTitle("Вооружение"); layout=QVBoxLayout(dialog); layout.addWidget(QLabel(person['fio']));
        for weapon in self.service.list_simple_history('weapons',employee_id):
            row=QHBoxLayout(); label=QLabel(f"{weapon['weapon_type']}   №{weapon['serial_number']}"); copy=QPushButton("Копировать"); copy.clicked.connect(lambda _=False, text=f"{weapon['weapon_type']} №{weapon['serial_number']}": QApplication.clipboard().setText(text)); row.addWidget(label); row.addWidget(copy); layout.addLayout(row)
        all_copy=QPushButton("Копировать всё"); all_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.service.weapon_text(employee_id))); layout.addWidget(all_copy); close=QPushButton("Закрыть"); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def open_staff_filter(self, index: int):
        if index == 0: return
        column = self.staff_headers[index]
        menu = QMenu(self)
        values = self.service.staff_filter_values(column, self.staff_search.text())
        current = self.staff_filters.get(column, set(values))
        for value in values:
            action = menu.addAction(value or "(пусто)")
            action.setCheckable(True); action.setChecked(value in current)
            def toggle(checked, value=value, values=values, column=column):
                selected=set(self.staff_filters.get(column, set(values)))
                if checked: selected.add(value)
                else: selected.discard(value)
                self.staff_filters[column]=selected
                self.refresh_staff()
            action.toggled.connect(toggle)
        menu.exec(self.mapToGlobal(self.rect().center()))

    def reset_staff_filters(self):
        self.staff_filters.clear(); self.staff_section.setCurrentText("Все"); self.staff_search.clear(); self.refresh_staff()

    def show_column_menu(self):
        menu=QMenu(self)
        for index, header in enumerate(self.staff_headers[1:], 1):
            action=menu.addAction(header); action.setCheckable(True); action.setChecked(not self.staff_table.isColumnHidden(index))
            action.toggled.connect(lambda visible, index=index: (self.staff_table.setColumnHidden(index, not visible), self.save_staff_layout()))
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def _restore_staff_layout(self):
        try:
            visible=json.loads(self.db.get_setting('shds_visible_columns','{}'))
            widths=json.loads(self.db.get_setting('shds_column_widths','{}'))
        except json.JSONDecodeError:
            visible, widths = {}, {}
        for index, header in enumerate(self.staff_headers[1:], 1):
            if header in visible: self.staff_table.setColumnHidden(index, not bool(visible[header]))
            if header in widths: self.staff_table.setColumnWidth(index, int(widths[header]))

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
            vacancy=choice.addButton("Выбрать существующую вакансию",QMessageBox.AcceptRole); create=choice.addButton("Создать новую штатную единицу",QMessageBox.ActionRole); leave=choice.addButton("Пока оставить без штатной единицы",QMessageBox.RejectRole); choice.exec()
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
            # В группу попадают только действующие работники — вакансии пропускаем.
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
        # Запись из группы нельзя редактировать отдельно — открываем группу.
        if batch_id:
            self.open_group(batch_id); return
        if EventDialog(self.service, self, event_id=event_id).exec(): self.refresh_all()
    def delete_event(self):
        selected = self._selected_event_row()
        if not selected: return
        event_id, batch_id = selected
        if batch_id:
            # Одиночное удаление части группы запрещено: предлагаем удалить всю группу.
            count = len(self.service.list_batch_events(batch_id))
            choice = QMessageBox.question(self, "Групповое назначение", f"Запись входит в групповое назначение. Удалить всю группу? Будет удалено записей: {count}.")
            if choice == QMessageBox.Yes:
                self.service.delete_batch_events(batch_id); self.refresh_all()
            return
        if QMessageBox.question(self, "Удалить событие", "Удалить выбранную запись?") == QMessageBox.Yes: self.service.delete_event(event_id); self.refresh_all()
    def copy_summary(self): QApplication.clipboard().setText(self.service.render_daily_text(self.summary_date.date().toString("yyyy-MM-dd"))); QMessageBox.information(self, "Готово", "Расход скопирован в буфер обмена.")
    def seed_demo(self):
        try: self.service.seed_demo_data(); self.refresh_all(); QMessageBox.information(self, "Демо", "Добавлены 4 вымышленных работника и несколько событий.")
        except ValueError as exc: QMessageBox.warning(self, "Демо", str(exc))


def run_app(db_path: Path):
    app = QApplication.instance() or QApplication([]); app.setApplicationName(APP_NAME); window = MainWindow(db_path); window.show(); return app.exec()
