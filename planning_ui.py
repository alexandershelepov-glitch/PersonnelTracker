"""Monthly planning workspace for PersonnelTracker v0.8.3-E.

The planner is a UI view over the existing employees/events tables.  It does
not introduce a second event store or change overlap/business rules: creation
and editing always go through the existing EventDialog/BatchGroupDialog.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from config import EVENT_TYPES


ABSENCE_TYPES = {
    "Отпуск", "Больничный", "Выходной", "Отгул", "Отсутствуют по иным причинам",
}
SERVICE_TYPES = {
    "Командировка", "ММ", "Другие объекты", "Организация деятельности",
}
TRAINING_TYPES = {
    "Начальная подготовка", "Самостоятельная подготовка", "Подготовка руководителей",
    "Плановая подготовка", "Иная подготовка", "Сдача периодической проверки",
    "Сдача медкомиссии",
}


def install_planning_ui(window: Any) -> None:
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtGui import QBrush
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QComboBox,
        QFrame,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QPushButton,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    if getattr(window, "_planning_ui_installed", False):
        return

    page = window.pages.widget(2)
    root = page.layout() if page is not None else None
    if root is None:
        return

    for label in page.findChildren(QLabel):
        if label.objectName() == "pageTitle":
            label.setText("Планирование")
            break

    # Preserve the legacy event page off-screen.  Its widgets and handlers are
    # still used by old callbacks/tests, but the user works with the new views.
    legacy = QWidget(page)
    legacy.setObjectName("legacyPlanningPage")
    legacy_root = QVBoxLayout(legacy)
    while root.count() > 1:
        item = root.takeAt(1)
        if item.widget() is not None:
            legacy_root.addWidget(item.widget())
        elif item.layout() is not None:
            legacy_root.addLayout(item.layout())
        elif item.spacerItem() is not None:
            legacy_root.addItem(item.spacerItem())
    legacy.hide()
    window.planning_legacy = legacy

    toolbar = QHBoxLayout()
    previous = QPushButton("‹")
    next_button = QPushButton("›")
    month_label = QLabel()
    month_label.setStyleSheet("font-size: 16px; font-weight: 600;")
    current_month = QPushButton("Текущий месяц")
    add_event = QPushButton("+ Добавить событие")
    add_event.setProperty("role", "primary")
    toolbar.addWidget(previous)
    toolbar.addWidget(month_label)
    toolbar.addWidget(next_button)
    toolbar.addWidget(current_month)
    toolbar.addStretch()
    toolbar.addWidget(add_event)
    root.addLayout(toolbar)

    filter_row = QHBoxLayout()
    department = QComboBox()
    section = QComboBox()
    event_type = QComboBox()
    for caption, combo in (
        ("Подразделение:", department),
        ("Отделение:", section),
        ("Событие:", event_type),
    ):
        filter_row.addWidget(QLabel(caption))
        filter_row.addWidget(combo)
    filter_row.addStretch()
    root.addLayout(filter_row)

    tabs = QTabWidget()
    root.addWidget(tabs, 1)
    window.planning_tabs = tabs

    # -------------------- Graph -------------------------------------------
    graph = QWidget()
    graph_root = QVBoxLayout(graph)
    graph_root.setContentsMargins(0, 8, 0, 0)
    graph_hint = QLabel(
        "Сотрудники расположены по строкам, дни месяца — по столбцам. "
        "Щёлкните по полосе события для просмотра/редактирования. "
        "Двойной щелчок по пустому дню создаёт событие с уже выбранными работником и датой."
    )
    graph_hint.setObjectName("secondaryText")
    graph_hint.setWordWrap(True)
    graph_root.addWidget(graph_hint)

    splitter = QSplitter(Qt.Horizontal)
    people = QTableWidget(0, 3)
    people.setHorizontalHeaderLabels(["ФИО", "Подразделение / отделение", "Должность"])
    people.setEditTriggers(QAbstractItemView.NoEditTriggers)
    people.setSelectionMode(QAbstractItemView.NoSelection)
    people.verticalHeader().hide()
    people.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    people.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    people.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    people.setMinimumWidth(500)

    days = QTableWidget(0, 31)
    days.setEditTriggers(QAbstractItemView.NoEditTriggers)
    days.setSelectionMode(QAbstractItemView.SingleSelection)
    days.verticalHeader().hide()
    days.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
    days.horizontalHeader().setDefaultSectionSize(42)
    days.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    splitter.addWidget(people)
    splitter.addWidget(days)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    graph_root.addWidget(splitter, 1)
    tabs.addTab(graph, "График")

    # Keep the two halves aligned vertically.
    people.verticalScrollBar().valueChanged.connect(days.verticalScrollBar().setValue)
    days.verticalScrollBar().valueChanged.connect(people.verticalScrollBar().setValue)

    # -------------------- List --------------------------------------------
    list_tab = QWidget()
    list_root = QVBoxLayout(list_tab)
    list_root.setContentsMargins(0, 8, 0, 0)
    list_actions = QHBoxLayout()
    list_search = QLineEdit()
    list_search.setPlaceholderText("ФИО, тип события, место, основание...")
    list_actions.addWidget(QLabel("Поиск:"))
    list_actions.addWidget(list_search, 1)
    list_root.addLayout(list_actions)
    event_list = QTableWidget(0, 9)
    event_list.setHorizontalHeaderLabels([
        "ФИО", "Тип", "Подтип", "С", "По", "Место / объект", "Основание", "Примечание", "ID",
    ])
    event_list.setColumnHidden(8, True)
    event_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
    event_list.setSelectionBehavior(QAbstractItemView.SelectRows)
    event_list.setSelectionMode(QAbstractItemView.SingleSelection)
    event_list.setAlternatingRowColors(True)
    event_list.verticalHeader().hide()
    event_list.horizontalHeader().setStretchLastSection(False)
    event_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    event_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    event_list.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
    list_root.addWidget(event_list, 1)
    tabs.addTab(list_tab, "Список")

    window.planning_people_table = people
    window.planning_days_table = days
    window.planning_list_table = event_list
    window.planning_department = department
    window.planning_section = section
    window.planning_event_type = event_type
    window.planning_search = list_search

    selected_month = {"date": QDate.currentDate().addDays(1 - QDate.currentDate().day())}
    event_cells: dict[tuple[int, int], int] = {}
    row_employee_ids: list[int] = []

    def fill_combo(combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Все")
        for value in values:
            clean = str(value or "").strip()
            if clean and clean != "—" and combo.findText(clean) < 0:
                combo.addItem(clean)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def refresh_filter_values() -> None:
        fill_combo(department, window.service.unique_field_values("department"))
        fill_combo(section, window.service.unique_field_values("section"))
        fill_combo(event_type, list(EVENT_TYPES.keys()))

    def month_bounds() -> tuple[str, str, int]:
        qmonth = selected_month["date"]
        year, month = qmonth.year(), qmonth.month()
        count = monthrange(year, month)[1]
        first = f"{year:04d}-{month:02d}-01"
        last = f"{year:04d}-{month:02d}-{count:02d}"
        return first, last, count

    def filtered_people() -> list[Any]:
        result = []
        for person in window.service.list_employees(include_archived=False):
            details = window.service.get_employee(int(person["id"])) or person
            dep = str(details["effective_department"] or details["department"] or "")
            sec = str(details["effective_section"] or details["section"] or "")
            if department.currentText() != "Все" and dep != department.currentText():
                continue
            if section.currentText() != "Все" and sec != section.currentText():
                continue
            result.append(details)
        return result

    def events_for_month(allowed_ids: set[int] | None = None) -> list[Any]:
        first, last, _ = month_bounds()
        result = []
        for event in window.service.list_events():
            if str(event["start_date"]) > last or str(event["end_date"]) < first:
                continue
            if allowed_ids is not None and int(event["employee_id"]) not in allowed_ids:
                continue
            if event_type.currentText() != "Все" and event["event_type"] != event_type.currentText():
                continue
            result.append(event)
        return result

    def category_role(event_name: str) -> str:
        if event_name in ABSENCE_TYPES:
            return "warning_bg"
        if event_name in SERVICE_TYPES:
            return "hover"
        if event_name in TRAINING_TYPES:
            return "alternate_row"
        return "attention_bg"

    def event_brush(event_name: str) -> QBrush:
        return QBrush(window.theme_manager.color(category_role(event_name)))

    def open_event_by_id(event_id: int) -> None:
        from ui import BatchGroupDialog, EventDialog
        event = window.service.get_event(int(event_id))
        if not event:
            return
        if event["batch_id"]:
            dialog = BatchGroupDialog(window.service, str(event["batch_id"]), window)
        else:
            dialog = EventDialog(
                window.service,
                parent=window,
                employee_id=int(event["employee_id"]),
                event_id=int(event_id),
            )
        dialog.exec()
        window.refresh_all()

    def open_new_event(employee_id: int | None = None, when: QDate | None = None) -> None:
        from ui import EventDialog
        dialog = EventDialog(window.service, parent=window, employee_id=employee_id)
        chosen = when or selected_month["date"]
        dialog.start.setDate(chosen)
        dialog.end.setDate(chosen)
        if dialog.exec():
            window.refresh_all()

    window.open_planning_event = open_event_by_id
    window.open_new_planning_event = open_new_event

    def refresh_graph() -> None:
        qmonth = selected_month["date"]
        month_label.setText(qmonth.toString("MMMM yyyy"))
        _, _, count = month_bounds()
        labels = []
        for day_no in range(1, count + 1):
            qday = QDate(qmonth.year(), qmonth.month(), day_no)
            labels.append(f"{day_no}\n{qday.toString('ddd')}")
        days.clearSpans()
        days.setColumnCount(count)
        days.setHorizontalHeaderLabels(labels)
        days.horizontalHeader().setDefaultSectionSize(44)

        persons = filtered_people()
        row_employee_ids.clear()
        row_employee_ids.extend(int(person["id"]) for person in persons)
        people.setRowCount(len(persons))
        days.setRowCount(len(persons))
        event_cells.clear()
        alternate = window.theme_manager.color("alternate_row")

        for row, person in enumerate(persons):
            dep = str(person["effective_department"] or person["department"] or "")
            sec = str(person["effective_section"] or person["section"] or "")
            organisation = " / ".join(value for value in (dep, sec) if value) or "—"
            values = [
                person["fio"] or "—",
                organisation,
                person["effective_position"] or person["position"] or "—",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, int(person["id"]))
                people.setItem(row, column, item)
            people.setRowHeight(row, 32)
            days.setRowHeight(row, 32)
            for day_col in range(count):
                qday = QDate(qmonth.year(), qmonth.month(), day_col + 1)
                cell = QTableWidgetItem("")
                if qday.dayOfWeek() in (6, 7):
                    cell.setBackground(alternate)
                days.setItem(row, day_col, cell)

        row_by_employee = {employee_id: row for row, employee_id in enumerate(row_employee_ids)}
        first, last, _ = month_bounds()
        for event in events_for_month(set(row_employee_ids)):
            employee_id = int(event["employee_id"])
            row = row_by_employee.get(employee_id)
            if row is None:
                continue
            visible_start = max(str(event["start_date"]), first)
            visible_end = min(str(event["end_date"]), last)
            start_date = date.fromisoformat(visible_start)
            end_date = date.fromisoformat(visible_end)
            start_col = start_date.day - 1
            span = end_date.day - start_date.day + 1
            label = str(event["event_type"])
            if event["subtype"]:
                label += f" / {event['subtype']}"
            item = QTableWidgetItem(label)
            item.setData(Qt.UserRole, int(event["id"]))
            item.setBackground(event_brush(str(event["event_type"])))
            period = f"{event['start_date']} — {event['end_date']}"
            location = f"\n{event['location']}" if event["location"] else ""
            item.setToolTip(f"{label}\n{period}{location}")
            days.setItem(row, start_col, item)
            if span > 1:
                days.setSpan(row, start_col, 1, span)
            for column in range(start_col, start_col + span):
                event_cells[(row, column)] = int(event["id"])

    def refresh_list() -> None:
        allowed = {int(person["id"]) for person in filtered_people()}
        needle = list_search.text().strip().casefold()
        rows = []
        for event in events_for_month(allowed):
            haystack = " ".join(
                str(event[key] or "")
                for key in ("fio", "event_type", "subtype", "location", "basis", "notes")
            ).casefold()
            if needle and needle not in haystack:
                continue
            rows.append(event)
        event_list.setRowCount(len(rows))
        for row, event in enumerate(rows):
            values = [
                event["fio"], event["event_type"], event["subtype"] or "—",
                event["start_date"], event["end_date"], event["location"] or "—",
                event["basis"] or "—", event["notes"] or "—", int(event["id"]),
            ]
            brush = event_brush(str(event["event_type"]))
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, int(event["id"]))
                if column < 8:
                    item.setBackground(brush)
                event_list.setItem(row, column, item)

    def refresh_planning(*_args) -> None:
        refresh_filter_values()
        refresh_graph()
        refresh_list()

    window.refresh_planning = refresh_planning

    def change_month(delta: int) -> None:
        selected_month["date"] = selected_month["date"].addMonths(delta)
        refresh_graph()
        refresh_list()

    previous.clicked.connect(lambda: change_month(-1))
    next_button.clicked.connect(lambda: change_month(1))
    current_month.clicked.connect(lambda: (
        selected_month.__setitem__("date", QDate.currentDate().addDays(1 - QDate.currentDate().day())),
        refresh_graph(), refresh_list(),
    ))
    add_event.clicked.connect(lambda: open_new_event(None, selected_month["date"]))
    for combo in (department, section, event_type):
        combo.currentTextChanged.connect(lambda _text: (refresh_graph(), refresh_list()))
    list_search.textChanged.connect(lambda _text: refresh_list())

    def day_clicked(row: int, column: int) -> None:
        event_id = event_cells.get((row, column))
        if event_id:
            open_event_by_id(event_id)

    def day_double_clicked(row: int, column: int) -> None:
        if event_cells.get((row, column)):
            return
        if not (0 <= row < len(row_employee_ids)):
            return
        qmonth = selected_month["date"]
        chosen = QDate(qmonth.year(), qmonth.month(), column + 1)
        if chosen.isValid():
            open_new_event(row_employee_ids[row], chosen)

    days.cellClicked.connect(day_clicked)
    days.cellDoubleClicked.connect(day_double_clicked)

    def list_double_clicked(row: int, _column: int) -> None:
        item = event_list.item(row, 0)
        event_id = item.data(Qt.UserRole) if item is not None else None
        if event_id:
            open_event_by_id(int(event_id))

    event_list.cellDoubleClicked.connect(list_double_clicked)

    original_refresh_all = window.refresh_all
    def refresh_all() -> None:
        original_refresh_all()
        refresh_graph()
        refresh_list()
    window.refresh_all = refresh_all

    original_sync = window._sync_theme_controls
    def sync_theme() -> None:
        original_sync()
        refresh_graph()
        refresh_list()
    window._sync_theme_controls = sync_theme

    refresh_filter_values()
    refresh_graph()
    refresh_list()
    window._planning_ui_installed = True
