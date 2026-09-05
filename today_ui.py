"""Daily landing page; all calculations remain in PersonnelService."""
from __future__ import annotations

from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtWidgets import (
    QCalendarWidget, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


class TodayPage(QScrollArea):
    def __init__(self, window):
        super().__init__()
        self.window = window
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
        note = QLabel("Расчёт по текущему штату на выбранный день. Выходные учитываются в отсутствиях. "
                      "Исторический состав доступен в разделе «Подробный расход».")
        note.setObjectName("secondaryText")
        note.setWordWrap(True)
        root.addWidget(note)

        self.people_grid = QGridLayout()
        self.absent_panel, self.absent = self.section("Отсутствуют")
        self.shift_panel, self.shift = self.section("На смене")
        self.people_grid.addWidget(self.absent_panel, 0, 0)
        self.people_grid.addWidget(self.shift_panel, 0, 1)
        self.people_grid.setColumnStretch(0, 1)
        self.people_grid.setColumnStretch(1, 1)
        root.addLayout(self.people_grid)
        attention_panel, self.attention = self.section("Требует внимания")
        root.addWidget(attention_panel)
        detail, detail_label = self.section("Подробный расход")
        detail_label.setText("Полная сводка, состояние на дату и история назначений.")
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

    def set_date(self, value):
        if value.isValid():
            self.selected_date = value
            self.refresh()

    def choose_date(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Выбрать дату")
        layout = QVBoxLayout(dialog)
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

    def open_event(self):
        # Reuse the working editor, with the day selected in the daily hub.
        from ui import EventDialog
        dialog = EventDialog(self.window.service, parent=self.window)
        dialog.start.setDate(self.selected_date)
        dialog.end.setDate(self.selected_date)
        dialog.exec()
        self.window.refresh_all()

    def open_details(self):
        self.window.summary_date.setDate(self.selected_date)
        self.window.state_date.setDate(self.selected_date)
        self.window._select_page(3)

    def refresh(self):
        service = self.window.service
        target = self.selected_date.toString("yyyy-MM-dd")
        self.date_label.setText(QLocale("ru_RU").toString(self.selected_date, "d MMMM yyyy, dddd"))
        metrics = service.staff_metrics(target)
        for key, label in self.values.items():
            label.setText(str(metrics["total"][key]))
        self.absent.setText("\n".join(f"{p.fio} — {p.label}" for p in metrics["absent"])
                            or "На выбранный день отсутствующих нет.")
        shifts = [p for p in metrics["present"] if p.source == "schedule" and p.status == "Работа"]
        self.shift.setText("\n".join(f"{p.fio} — {p.position}" for p in shifts)
                           or "На выбранный день смены по графику не назначены.")
        warnings = []
        unassigned = service.unassigned_active_employees()
        if unassigned:
            warnings.append(f"Без штатного назначения: {len(unassigned)}.")
        unknown = [p for p in metrics["present"] if p.source == "default"]
        if unknown:
            warnings.append(f"График не задан: {len(unknown)}. Нахождение на смене не подтверждено.")
        if not metrics["valid"]:
            warnings.append("Есть расхождение в сводке личного состава.")
        self.attention.setText("\n".join(warnings) or "Расхождений в сводке и неназначенных работников нет.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.viewport().width() < 900
        self.header.addWidget(self.actions, 1 if compact else 0, 0 if compact else 1)
        self.people_grid.addWidget(self.shift_panel, 1 if compact else 0, 0 if compact else 1)
        self.people_grid.setColumnStretch(1, 0 if compact else 1)


def install_today_ui(window):
    """Retain legacy page indexes: existing callbacks still address 0..4."""
    page = TodayPage(window)
    window.today_page = page
    today_index = window.pages.addWidget(page)
    sidebar = window.findChild(QFrame, "sidebar")
    sidebar.setMinimumWidth(180)
    sidebar.setMaximumWidth(220)
    today = QPushButton("Сегодня")
    today.setCheckable(True)
    today.setProperty("navButton", True)
    today.clicked.connect(lambda: window._select_page(today_index))
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
    def select(index):
        original_select(index)
        window.nav_group.button({1: 0, 3: today_index}.get(index, index)).setChecked(True)
        if index == today_index:
            page.refresh()
    window._select_page = select
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
        """)
    original_sync = window._sync_theme_controls
    def sync_theme():
        original_sync()
        style()
    window._sync_theme_controls = sync_theme
    style()
    window._select_page(today_index)
