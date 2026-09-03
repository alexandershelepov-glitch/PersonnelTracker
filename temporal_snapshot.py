from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from assignment_history import AssignmentHistoryService
from config import UNAVAILABLE_EVENT_TYPES
from database import Database
from services import PersonnelService


@dataclass(frozen=True)
class PersonnelStateRow:
    employee_id: int
    fio: str
    personnel_no: str
    unit_number: str
    department: str
    section: str
    group_name: str
    position: str
    schedule_type: str
    status: str
    subtype: str
    location: str
    availability: str
    source: str

    @property
    def status_text(self) -> str:
        return f"{self.status}: {self.subtype}" if self.subtype else self.status


@dataclass(frozen=True)
class PersonnelStateSummary:
    total: int
    assigned: int
    unassigned: int
    available: int
    unavailable: int
    needs_check: int


class TemporalPersonnelService:
    """Resolve a truthful personnel state for one day within the v0.8 history window.

    Assignment placement comes from staff_assignments.  Day status comes from
    the existing events table and employee work schedule.  No separate absence
    journal is introduced here.
    """

    def __init__(self, db: Database, history: AssignmentHistoryService | None = None):
        self.db = db
        self.history = history or AssignmentHistoryService(db)
        self.personnel = PersonnelService(db)

    def _validate_target(self, target_date: str) -> date:
        try:
            target = date.fromisoformat(target_date)
        except ValueError as exc:
            raise ValueError("Некорректная дата среза.") from exc
        if target < self.history.tracking_started_date:
            raise ValueError(
                "Полный срез доступен только с "
                + self.history.tracking_started_date.strftime("%d.%m.%Y")
                + ", когда начался учёт истории v0.8."
            )
        if target > date.today():
            raise ValueError("Нельзя построить срез на будущую дату.")
        return target

    @staticmethod
    def _active_on_date(person: Any, target: date) -> bool:
        employment_date = person["employment_date"]
        if employment_date:
            try:
                if target < date.fromisoformat(str(employment_date)):
                    return False
            except ValueError:
                pass
        archive_date = person["archive_date"]
        if archive_date:
            try:
                # archive_date is the first day the employee is no longer active.
                if target >= date.fromisoformat(str(archive_date)):
                    return False
            except ValueError:
                pass
        return True

    def _schedule_state(self, person: Any, target: date) -> tuple[str, str, str]:
        schedule = (person["schedule_type"] or "Не задан").strip()
        if schedule == "1/3":
            anchor = person["schedule_anchor_date"]
            if not anchor:
                return "График 1/3 — нет опорной смены", "Требует проверки", "schedule"
            try:
                work = self.personnel.is_workday_13(target, date.fromisoformat(str(anchor)))
            except ValueError:
                return "График 1/3 — неверная опорная дата", "Требует проверки", "schedule"
            return (
                ("Работа", "Доступен", "schedule")
                if work
                else ("Выходной", "Недоступен", "schedule")
            )
        if schedule == "5/2":
            return (
                ("Работа", "Доступен", "schedule")
                if target.weekday() < 5
                else ("Выходной", "Недоступен", "schedule")
            )
        return "Работа / график не задан", "Требует проверки", "default"

    def _events_for_day(self, target_date: str) -> dict[int, Any]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM events
                WHERE start_date<=? AND end_date>=?
                ORDER BY id DESC
                """,
                (target_date, target_date),
            ).fetchall()
        # Existing event validation forbids overlaps for one employee.  Keep the
        # newest row if an old database somehow contains duplicates.
        result: dict[int, Any] = {}
        for row in rows:
            result.setdefault(int(row["employee_id"]), row)
        return result

    def _people_for_day(self, target: date) -> dict[int, Any]:
        with self.db.connect() as connection:
            rows = connection.execute("SELECT * FROM employees ORDER BY fio COLLATE NOCASE").fetchall()
        return {
            int(row["id"]): row
            for row in rows
            if self._active_on_date(row, target)
        }

    def states(self, target_date: str) -> list[PersonnelStateRow]:
        target = self._validate_target(target_date)
        people = self._people_for_day(target)
        events = self._events_for_day(target_date)
        assignments = self.history.snapshot(target_date)
        assignment_by_employee = {
            int(row["employee_id"]): row
            for row in assignments
            if int(row["employee_id"]) in people
        }

        result: list[PersonnelStateRow] = []
        for employee_id, person in people.items():
            assignment = assignment_by_employee.get(employee_id)
            event = events.get(employee_id)
            if event is not None:
                status = str(event["event_type"] or "")
                subtype = str(event["subtype"] or "")
                location = str(event["location"] or "")
                availability = "Недоступен" if status in UNAVAILABLE_EVENT_TYPES else "Доступен"
                source = "event"
            else:
                status, availability, source = self._schedule_state(person, target)
                subtype = ""
                location = ""

            if assignment is not None:
                unit_number = str(assignment["unit_number"] or "")
                department = str(assignment["department"] or "")
                section = str(assignment["section"] or "")
                group_name = str(assignment["group_name"] or "")
                position = str(assignment["position"] or "")
            else:
                unit_number = "ВНЕ ШДС"
                # Current free-text organisation data is useful for an unassigned
                # person, but is not presented as a historical staff-unit fact.
                department = str(person["department"] or "")
                section = str(person["section"] or "")
                group_name = str(person["group_name"] or "")
                position = str(person["position"] or "")

            result.append(
                PersonnelStateRow(
                    employee_id=employee_id,
                    fio=str(person["fio"] or ""),
                    personnel_no=str(person["personnel_no"] or ""),
                    unit_number=unit_number,
                    department=department,
                    section=section,
                    group_name=group_name,
                    position=position,
                    schedule_type=str(person["schedule_type"] or "Не задан"),
                    status=status,
                    subtype=subtype,
                    location=location,
                    availability=availability,
                    source=source,
                )
            )

        return sorted(
            result,
            key=lambda row: (
                row.section.casefold(),
                row.group_name.casefold(),
                row.unit_number.casefold(),
                row.fio.casefold(),
            ),
        )

    def summary(self, target_date: str) -> PersonnelStateSummary:
        rows = self.states(target_date)
        assigned = sum(row.unit_number != "ВНЕ ШДС" for row in rows)
        available = sum(row.availability == "Доступен" for row in rows)
        unavailable = sum(row.availability == "Недоступен" for row in rows)
        needs_check = sum(row.availability == "Требует проверки" for row in rows)
        return PersonnelStateSummary(
            total=len(rows),
            assigned=assigned,
            unassigned=len(rows) - assigned,
            available=available,
            unavailable=unavailable,
            needs_check=needs_check,
        )


def install_temporal_snapshot_features(window: Any) -> None:
    """Add v0.8.2 personnel-state UI to the Service page."""
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import (
        QComboBox,
        QDateEdit,
        QDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )

    history = getattr(window, "assignment_history", None)
    service = TemporalPersonnelService(window.db, history=history)
    window.temporal_personnel = service

    class StateDialog(QDialog):
        HEADERS = [
            "ШЕ №", "Подразделение", "Отделение", "Группа", "Должность",
            "ФИО", "Таб. №", "График", "Статус", "Место / объект", "Доступность",
        ]

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Состояние личного состава на дату")
            self.resize(1320, 700)
            root = QVBoxLayout(self)

            controls = QHBoxLayout()
            self.when = QDateEdit(calendarPopup=True)
            self.when.setDisplayFormat("dd.MM.yyyy")
            self.when.setMinimumDate(
                QDate.fromString(service.history.tracking_started_date.isoformat(), "yyyy-MM-dd")
            )
            self.when.setMaximumDate(QDate.currentDate())
            self.when.setDate(QDate.currentDate())
            self.filter = QComboBox()
            self.filter.addItems(["Все", "Доступен", "Недоступен", "Требует проверки"])
            show = QPushButton("Показать")
            show.setProperty("role", "primary")
            show.clicked.connect(self.reload)
            self.filter.currentIndexChanged.connect(self.reload)
            controls.addWidget(QLabel("Дата:"))
            controls.addWidget(self.when)
            controls.addWidget(QLabel("Доступность:"))
            controls.addWidget(self.filter)
            controls.addWidget(show)
            controls.addStretch()
            root.addLayout(controls)

            self.summary_label = QLabel()
            self.summary_label.setWordWrap(True)
            root.addWidget(self.summary_label)
            hint = QLabel(
                "Событие на выбранную дату имеет приоритет над графиком. "
                "Для 1/3 смена считается от опорной даты, для 5/2 — по дням недели. "
                "Работники без штатного назначения показываются как «ВНЕ ШДС»."
            )
            hint.setWordWrap(True)
            hint.setObjectName("secondaryText")
            root.addWidget(hint)

            self.table = QTableWidget(0, len(self.HEADERS))
            self.table.setHorizontalHeaderLabels(self.HEADERS)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)
            self.table.horizontalHeader().setStretchLastSection(True)
            root.addWidget(self.table, 1)

            close = QPushButton("Закрыть")
            close.clicked.connect(self.accept)
            bottom = QHBoxLayout(); bottom.addStretch(); bottom.addWidget(close); root.addLayout(bottom)
            self.reload()

        def reload(self):
            iso = self.when.date().toString("yyyy-MM-dd")
            try:
                all_rows = service.states(iso)
                summary = service.summary(iso)
            except ValueError as exc:
                QMessageBox.warning(self, "Состояние на дату", str(exc))
                return
            self.summary_label.setText(
                f"Всего работников: {summary.total} · В ШДС: {summary.assigned} · Вне ШДС: {summary.unassigned} · "
                f"Доступны: {summary.available} · Недоступны: {summary.unavailable} · "
                f"Требуют проверки графика: {summary.needs_check}"
            )
            selected = self.filter.currentText()
            rows = all_rows if selected == "Все" else [row for row in all_rows if row.availability == selected]
            self.table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                values = [
                    row.unit_number,
                    row.department or "—",
                    row.section or "—",
                    row.group_name or "—",
                    row.position or "—",
                    row.fio,
                    row.personnel_no,
                    row.schedule_type,
                    row.status_text,
                    row.location or "—",
                    row.availability,
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    self.table.setItem(row_index, column, item)
            self.table.resizeColumnsToContents()

    def open_state():
        StateDialog(window).exec()

    page = window.pages.widget(4)
    layout = page.layout()
    box = QGroupBox("Состояние личного состава на дату — v0.8.2")
    box_layout = QVBoxLayout(box)
    description = QLabel(
        "Показывает штатное назначение и фактический статус каждого работника на выбранный день: "
        "работа, выходной, отпуск, больничный, командировка, мероприятие или другое зарегистрированное событие."
    )
    description.setWordWrap(True)
    box_layout.addWidget(description)
    actions = QHBoxLayout()
    button = QPushButton("Открыть состояние на дату")
    button.setProperty("role", "primary")
    button.clicked.connect(open_state)
    actions.addWidget(button); actions.addStretch(); box_layout.addLayout(actions)
    layout.insertWidget(max(0, layout.count() - 1), box)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addAction("Состояние личного состава на дату", open_state)
