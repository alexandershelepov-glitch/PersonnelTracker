"""Operational daily landing page for PersonnelTracker v0.8.3."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from today_state import TodayStateService


def _format_iso(value: str) -> str:
    parsed = QDate.fromString(value or "", "yyyy-MM-dd")
    return parsed.toString("dd.MM.yyyy") if parsed.isValid() else (value or "—")


class PeopleListDialog(QDialog):
    """Small contextual list used by actionable Today warnings."""

    def __init__(self, page, title: str, rows: list[dict], parent=None):
        super().__init__(parent)
        self.page = page
        self.rows = rows
        self.setWindowTitle(title)
        self.resize(760, 460)
        root = QVBoxLayout(self)
        back = QPushButton("← Назад")
        back.clicked.connect(self.reject)
        root.addWidget(back, 0, Qt.AlignLeft)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        root.addWidget(heading)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ФИО", "Что требует внимания", "Дополнительно"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self.open_selected)
        root.addWidget(self.table, 1)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [row.get("fio", "—"), row.get("detail", "—"), row.get("extra", "—")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or "—"))
                if column == 0:
                    item.setData(Qt.UserRole, row.get("employee_id"))
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()

    def open_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        employee_id = self.table.item(row, 0).data(Qt.UserRole)
        if employee_id:
            self.page.open_employee(int(employee_id))


class TodayPage(QScrollArea):
    ATTENTION_WINDOW_DAYS = 7
    CONTROL_PERIOD_DAYS = 365
    CONTROL_WARNING_DAYS = 30

    def __init__(self, window):
        super().__init__()
        self.window = window
        temporal = getattr(window, "temporal_personnel", None)
        if temporal is None:
            from temporal_snapshot import TemporalPersonnelService
            temporal = TemporalPersonnelService(window.db)
        self.day_state = TodayStateService(window.service, temporal)
        self.selected_date = QDate.currentDate()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("todayBody")
        self.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)
        title = QLabel("Сегодня")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self.header = QGridLayout()
        dates = QWidget()
        date_row = QHBoxLayout(dates)
        date_row.setContentsMargins(0, 0, 0, 0)
        self.previous = QPushButton("‹")
        self.previous.setAccessibleName("Предыдущий день")
        self.next = QPushButton("›")
        self.next.setAccessibleName("Следующий день")
        self.date_label = QLabel()
        self.date_label.setObjectName("todayDate")
        self.date_label.setWordWrap(True)
        self.calendar = QPushButton("Календарь")
        self.reset = QPushButton("Сегодня")
        self.previous.clicked.connect(lambda: self.set_date(self.selected_date.addDays(-1)))
        self.next.clicked.connect(lambda: self.set_date(self.selected_date.addDays(1)))
        self.reset.clicked.connect(lambda: self.set_date(QDate.currentDate()))
        self.calendar.clicked.connect(self.choose_date)
        for control in (self.previous, self.date_label, self.next, self.calendar, self.reset):
            date_row.addWidget(control)
        date_row.setStretch(1, 1)
        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()
        self.add_event = QPushButton("+ Добавить событие")
        self.add_event.setProperty("role", "primary")
        self.add_event.clicked.connect(self.open_event)
        self.team = QPushButton("Сформировать команду")
        self.team.clicked.connect(lambda: QMessageBox.information(
            self, "Сформировать команду",
            "Формирование команды появится на следующем этапе разработки."))
        actions.addWidget(self.add_event)
        actions.addWidget(self.team)
        self.header.addWidget(dates, 0, 0)
        self.header.addWidget(self.actions, 0, 1)
        self.header.setColumnStretch(0, 1)
        root.addLayout(self.header)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.values = {}
        for caption, key in (("По штату", "staff"), ("По списку", "listed"),
                             ("В наличии", "present"), ("Отсутствуют", "absent"),
                             ("Вакансии", "vacant")):
            card = QFrame()
            card.setObjectName("todayMetric")
            column = QVBoxLayout(card)
            label = QLabel(caption)
            label.setObjectName("metricCaption")
            label.setWordWrap(True)
            value = QLabel("—")
            value.setObjectName("metricValue")
            column.addWidget(label)
            column.addWidget(value)
            metrics.addWidget(card, 1)
            self.values[key] = value
        root.addLayout(metrics)
        note = QLabel(
            "Сводка строится по текущей ШДС, зарегистрированным событиям и графику на выбранный день. "
            "График 1/3 и 5/2 рассчитывается по правилам временного среза v0.8.2; "
            "не заданный график не считается подтверждённым наличием."
        )
        note.setObjectName("secondaryText")
        note.setWordWrap(True)
        root.addWidget(note)

        self.people_grid = QGridLayout()
        self.absent_panel, self.absent_table = self.table_section(
            "Отсутствуют", ["ФИО", "Причина", "Период", "Место / объект"]
        )
        self.shift_panel, self.shift_table = self.table_section(
            "На смене", ["ФИО", "Должность", "Подразделение"]
        )
        self.absent_table.cellClicked.connect(self.absent_clicked)
        self.shift_table.cellClicked.connect(self.shift_clicked)
        self.people_grid.addWidget(self.absent_panel, 0, 0)
        self.people_grid.addWidget(self.shift_panel, 0, 1)
        self.people_grid.setColumnStretch(0, 1)
        self.people_grid.setColumnStretch(1, 1)
        root.addLayout(self.people_grid)

        self.attention_panel = QFrame()
        self.attention_panel.setObjectName("todaySection")
        self.attention_layout = QVBoxLayout(self.attention_panel)
        self.attention_layout.setContentsMargins(16, 16, 16, 16)
        self.attention_layout.setSpacing(8)
        attention_title = QLabel("Требует внимания")
        attention_title.setObjectName("todaySectionTitle")
        self.attention_layout.addWidget(attention_title)
        self.attention_empty = QLabel()
        self.attention_empty.setWordWrap(True)
        self.attention_layout.addWidget(self.attention_empty)
        self.attention_buttons: list[QPushButton] = []
        root.addWidget(self.attention_panel)

        detail, detail_label = self.section("Подробный расход")
        detail_label.setText("Полная сводка и состояние личного состава по выбранной дате.")
        open_detail = QPushButton("Открыть подробный расход")
        open_detail.clicked.connect(self.open_details)
        detail.layout().addWidget(open_detail, 0, Qt.AlignLeft)
        root.addWidget(detail)
        root.addStretch()
        self.refresh()

    @staticmethod
    def section(title):
        panel = QFrame()
        panel.setObjectName("todaySection")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("todaySectionTitle")
        text = QLabel()
        text.setTextFormat(Qt.PlainText)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(heading)
        layout.addWidget(text)
        return panel, text

    @staticmethod
    def table_section(title: str, headers: list[str]):
        panel = QFrame()
        panel.setObjectName("todaySection")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("todaySectionTitle")
        layout.addWidget(heading)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(170)
        layout.addWidget(table)
        return panel, table

    def set_date(self, value):
        if value.isValid():
            self.selected_date = value
            self.refresh()

    def choose_date(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Выбрать дату")
        layout = QVBoxLayout(dialog)
        back = QPushButton("← Назад")
        back.clicked.connect(dialog.reject)
        layout.addWidget(back, 0, Qt.AlignLeft)
        calendar = QCalendarWidget()
        calendar.setLocale(QLocale("ru_RU"))
        calendar.setSelectedDate(self.selected_date)
        layout.addWidget(calendar)
        accept = QPushButton("Выбрать")
        accept.clicked.connect(dialog.accept)
        calendar.activated.connect(lambda _date: dialog.accept())
        layout.addWidget(accept)
        if dialog.exec() == QDialog.Accepted:
            self.set_date(calendar.selectedDate())

    @staticmethod
    def _mark_dialog_back(dialog: QDialog) -> None:
        """Modal dialogs already preserve caller state; label that return explicitly."""
        for button in dialog.findChildren(QPushButton):
            if button.text() in {"Закрыть", "Отмена"}:
                button.setText("← Назад")
        for box in dialog.findChildren(QDialogButtonBox):
            cancel = box.button(QDialogButtonBox.Cancel)
            if cancel is not None:
                cancel.setText("← Назад")

    def open_employee(self, employee_id: int):
        from ui import EmployeeDialog
        dialog = EmployeeDialog(self.window.service, employee_id, self.window)
        self._mark_dialog_back(dialog)
        dialog.exec()
        self.window.refresh_all()

    def open_event(self):
        from ui import EventDialog
        dialog = EventDialog(self.window.service, parent=self.window)
        dialog.start.setDate(self.selected_date)
        dialog.end.setDate(self.selected_date)
        self._mark_dialog_back(dialog)
        dialog.exec()
        self.window.refresh_all()

    def open_existing_event(self, event_id: int):
        from ui import BatchGroupDialog, EventDialog
        event = self.window.service.get_event(event_id)
        if not event:
            return
        if event["batch_id"]:
            dialog = BatchGroupDialog(self.window.service, str(event["batch_id"]), self.window)
        else:
            dialog = EventDialog(
                self.window.service,
                parent=self.window,
                employee_id=int(event["employee_id"]),
                event_id=event_id,
            )
        self._mark_dialog_back(dialog)
        dialog.exec()
        self.window.refresh_all()

    def open_details(self):
        self.window.summary_date.setDate(self.selected_date)
        self.window.state_date.setDate(self.selected_date)
        self.window._select_page(3)

    def absent_clicked(self, row: int, column: int):
        employee_id = self.absent_table.item(row, 0).data(Qt.UserRole)
        event_id = self.absent_table.item(row, 1).data(Qt.UserRole)
        if column == 0 and employee_id:
            self.open_employee(int(employee_id))
        elif event_id:
            self.open_existing_event(int(event_id))

    def shift_clicked(self, row: int, _column: int):
        employee_id = self.shift_table.item(row, 0).data(Qt.UserRole)
        if employee_id:
            self.open_employee(int(employee_id))

    def _fill_absent(self, rows):
        self.absent_table.setRowCount(len(rows))
        for row_index, person in enumerate(rows):
            period = (
                f"{_format_iso(person.start_date)} — {_format_iso(person.end_date)}"
                if person.event_id else _format_iso(self.selected_date.toString("yyyy-MM-dd"))
            )
            values = [person.fio, person.status_text, period, person.location or "—"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, person.employee_id)
                if column == 1:
                    item.setData(Qt.UserRole, person.event_id)
                self.absent_table.setItem(row_index, column, item)
        self.absent_table.resizeColumnsToContents()

    def _fill_shift(self, rows):
        self.shift_table.setRowCount(len(rows))
        for row_index, person in enumerate(rows):
            values = [person.fio, person.position or "—", person.section or person.department or "—"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, person.employee_id)
                self.shift_table.setItem(row_index, column, item)
        self.shift_table.resizeColumnsToContents()

    def _control_rows(self, target: date, kind: str) -> list[dict]:
        rows = []
        for person in self.window.service.list_employees(include_archived=False):
            medical, periodic = self.window.service.latest_check_dates(int(person["id"]))
            value = medical if kind == "medical" else periodic
            if not value:
                continue
            try:
                last = date.fromisoformat(str(value))
            except ValueError:
                continue
            due = last + timedelta(days=self.CONTROL_PERIOD_DAYS)
            days = (due - target).days
            if days <= self.CONTROL_WARNING_DAYS:
                state = "просрочено" if days < 0 else f"осталось {days} дн."
                rows.append({
                    "employee_id": int(person["id"]),
                    "fio": person["fio"],
                    "detail": "Медкомиссия" if kind == "medical" else "Периодическая проверка",
                    "extra": f"Срок {_format_iso(due.isoformat())} · {state}",
                })
        return rows

    def _attention_groups(self, snapshot) -> list[tuple[str, list[dict]]]:
        target_text = self.selected_date.toString("yyyy-MM-dd")
        target = date.fromisoformat(target_text)
        groups: list[tuple[str, list[dict]]] = []

        unassigned = [
            {"employee_id": int(person["id"]), "fio": person["fio"],
             "detail": "Нет штатного назначения", "extra": person["position"] or "—"}
            for person in self.window.service.unassigned_active_employees()
        ]
        if unassigned:
            groups.append(("Без штатной единицы", unassigned))

        unknown = [
            {"employee_id": person.employee_id, "fio": person.fio,
             "detail": person.status, "extra": person.position or "—"}
            for person in snapshot.rows if person.availability == "Требует проверки"
        ]
        if unknown:
            groups.append(("График не задан / требует проверки", unknown))

        end_limit = target + timedelta(days=self.ATTENTION_WINDOW_DAYS)
        ending = []
        for event in self.window.service.list_events():
            try:
                event_end = date.fromisoformat(str(event["end_date"]))
            except ValueError:
                continue
            if target <= event_end <= end_limit:
                ending.append({
                    "employee_id": int(event["employee_id"]),
                    "fio": event["fio"],
                    "detail": event["event_type"] + (f" / {event['subtype']}" if event["subtype"] else ""),
                    "extra": f"Заканчивается {_format_iso(str(event['end_date']))}",
                })
        if ending:
            groups.append((f"Событие заканчивается в течение {self.ATTENTION_WINDOW_DAYS} дней", ending))

        medical = self._control_rows(target, "medical")
        if medical:
            groups.append(("Медкомиссия требует внимания", medical))
        periodic = self._control_rows(target, "periodic")
        if periodic:
            groups.append(("Периодическая проверка требует внимания", periodic))

        conflicts = self.day_state.duplicate_event_people(target_text)
        if conflicts:
            groups.append(("Конфликт событий", conflicts))
        return groups

    def _set_attention(self, groups: list[tuple[str, list[dict]]]):
        for button in self.attention_buttons:
            self.attention_layout.removeWidget(button)
            button.deleteLater()
        self.attention_buttons.clear()
        if not groups:
            self.attention_empty.setText("На выбранный день нет зарегистрированных ситуаций, требующих действия.")
            self.attention_empty.show()
            return
        self.attention_empty.hide()
        for title, rows in groups:
            button = QPushButton(f"{title} — {len(rows)}")
            button.setProperty("attentionButton", True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, t=title, r=rows: PeopleListDialog(self, t, r, self.window).exec()
            )
            self.attention_layout.addWidget(button, 0, Qt.AlignLeft)
            self.attention_buttons.append(button)

    def refresh(self):
        target = self.selected_date.toString("yyyy-MM-dd")
        self.date_label.setText(QLocale("ru_RU").toString(self.selected_date, "d MMMM yyyy, dddd"))
        snapshot = self.day_state.snapshot(target)
        for key, label in self.values.items():
            label.setText(str(getattr(snapshot, key)))

        absent = [row for row in snapshot.rows if row.availability == "Недоступен"]
        shifts = [
            row for row in snapshot.rows
            if row.source == "schedule" and row.status == "Работа" and row.availability == "Доступен"
        ]
        self._fill_absent(absent)
        self._fill_shift(shifts)
        self._set_attention(self._attention_groups(snapshot))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.viewport().width() < 900
        self.header.addWidget(self.actions, 1 if compact else 0, 0 if compact else 1)
        self.people_grid.addWidget(self.shift_panel, 1 if compact else 0, 0 if compact else 1)
        self.people_grid.setColumnStretch(1, 0 if compact else 1)


def install_today_ui(window):
    """Install the Today hub while preserving legacy page indexes for callbacks."""
    page = TodayPage(window)
    window.today_page = page
    today_index = window.pages.addWidget(page)
    sidebar = window.findChild(QFrame, "sidebar")
    sidebar.setMinimumWidth(180)
    sidebar.setMaximumWidth(220)
    today = QPushButton("Сегодня")
    today.setCheckable(True)
    today.setProperty("navButton", True)
    window.nav_group.addButton(today, today_index)
    sidebar.layout().insertWidget(2, today)
    window.nav_buttons[0].setText("Состав")
    window.nav_buttons[1].hide()
    window.nav_buttons[3].hide()
    window.nav_buttons.append(today)
    for label in sidebar.findChildren(QLabel):
        if label.text() == "v0.6":
            label.setText("v0.8.3")
    window.setWindowTitle("PersonnelTracker — v0.8.3")

    # Keep employee cards accessible inside Composition without rebuilding it.
    staff_page = window.pages.widget(0)
    workers = QPushButton("Открыть работников")
    workers.clicked.connect(lambda: window._select_page(1))
    staff_page.layout().insertWidget(1, workers)

    original_select = window._select_page
    root_indexes = {0, 2, 4, today_index}
    parent_button = {1: 0, 3: today_index}
    window._navigation_stack = []

    def update_back_buttons():
        current = window.pages.currentIndex()
        for index, button in getattr(window, "_nested_back_buttons", {}).items():
            button.setVisible(current == index)

    def select(index, record_history=True):
        current = window.pages.currentIndex()
        if record_history and index not in root_indexes and current != index:
            if not window._navigation_stack or window._navigation_stack[-1] != current:
                window._navigation_stack.append(current)
        original_select(index)
        button = window.nav_group.button(parent_button.get(index, index))
        if button is not None:
            button.setChecked(True)
        if index == today_index:
            page.refresh()
        update_back_buttons()

    def navigate_root(index):
        window._navigation_stack.clear()
        select(index, record_history=False)

    def navigate_back():
        target = window._navigation_stack.pop() if window._navigation_stack else today_index
        select(target, record_history=False)

    window._select_page = select
    window.navigate_back = navigate_back
    window._nested_back_buttons = {}

    # Rewire the visible sidebar buttons as roots: selecting one starts a fresh
    # navigation context and therefore never shows a Back action on that root.
    for index in root_indexes:
        button = window.nav_group.button(index)
        if button is None:
            continue
        try:
            button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        button.clicked.connect(lambda _checked=False, i=index: navigate_root(i))

    for nested_index in (1, 3):
        nested_page = window.pages.widget(nested_index)
        if nested_page is None or nested_page.layout() is None:
            continue
        back = QPushButton("← Назад")
        back.clicked.connect(navigate_back)
        nested_page.layout().insertWidget(0, back, 0, Qt.AlignLeft)
        window._nested_back_buttons[nested_index] = back

    original_refresh = window.refresh_all
    def refresh_all():
        original_refresh()
        page.refresh()
    window.refresh_all = refresh_all

    # Scoped styling uses the existing palette; both themes keep one accent.
    def style():
        color = lambda role: window.theme_manager.color(role).name()
        page.setStyleSheet(f"""
            QWidget#todayBody {{ background: {color('window_bg')}; }}
            QFrame#todayMetric, QFrame#todaySection {{
                background: {color('panel_bg')}; border: none; border-radius: 10px;
            }}
            QLabel#todayDate {{ font-size: 17px; font-weight: 600; }}
            QLabel#todaySectionTitle {{ font-size: 15px; font-weight: 600; }}
            QPushButton[attentionButton="true"] {{ text-align: left; padding: 8px 10px; }}
        """)
    original_sync = window._sync_theme_controls
    def sync_theme():
        original_sync()
        style()
    window._sync_theme_controls = sync_theme
    style()
    navigate_root(today_index)
