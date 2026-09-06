"""Manual team formation workspace for PersonnelTracker v0.8.3-F.

The UI deliberately reuses two existing sources of truth:
- TodayStateService resolves the selected-day personnel state and schedules;
- BatchEventDialog / PersonnelService keep the existing conflict and
  transactional all-or-nothing rules for group event creation.

No team roster or second event store is persisted by this module.
"""
from __future__ import annotations

from typing import Any


def install_manual_team_ui(window: Any) -> None:
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDateEdit,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    if getattr(window, "_manual_team_ui_installed", False):
        return
    tabs = getattr(window, "composition_tabs", None)
    if tabs is None or tabs.count() < 2:
        return

    # Replace only the v0.8.3-C placeholder. The outer Composition workflow,
    # Directory and SHDS tabs remain untouched.
    old_team = tabs.widget(1)
    team_tab = QWidget()
    tabs.removeTab(1)
    tabs.insertTab(1, team_tab, "Сформировать команду")
    if old_team is not None:
        old_team.setParent(None)
        old_team.deleteLater()
    window.composition_team_tab = team_tab

    root = QVBoxLayout(team_tab)
    root.setContentsMargins(0, 8, 0, 0)
    root.setSpacing(10)

    mode_tabs = QTabWidget()
    root.addWidget(mode_tabs, 1)

    # -------------------- Manual mode -------------------------------------
    manual = QWidget()
    manual_root = QVBoxLayout(manual)
    manual_root.setContentsMargins(8, 10, 8, 8)
    manual_root.setSpacing(10)
    mode_tabs.addTab(manual, "Ручной режим")

    intro = QLabel(
        "Выберите дату и отметьте работников вручную. Состояние на день "
        "рассчитывается тем же механизмом, что и экран «Сегодня». "
        "Кандидаты берутся из действующего списочного состава ШДС."
    )
    intro.setObjectName("secondaryText")
    intro.setWordWrap(True)
    manual_root.addWidget(intro)

    top = QHBoxLayout()
    team_date = QDateEdit()
    team_date.setCalendarPopup(True)
    team_date.setDisplayFormat("dd.MM.yyyy")
    team_date.setDate(QDate.currentDate())
    search = QLineEdit()
    search.setPlaceholderText("ФИО или табельный номер...")
    top.addWidget(QLabel("Дата:"))
    top.addWidget(team_date)
    top.addWidget(QLabel("Поиск:"))
    top.addWidget(search, 1)
    manual_root.addLayout(top)

    filters = QHBoxLayout()
    department = QComboBox()
    section = QComboBox()
    group = QComboBox()
    position = QComboBox()
    schedule = QComboBox()
    for caption, combo in (
        ("Подразделение:", department),
        ("Отделение:", section),
        ("Группа:", group),
        ("Должность:", position),
        ("График:", schedule),
    ):
        combo.setMinimumWidth(105)
        filters.addWidget(QLabel(caption))
        filters.addWidget(combo)
    filters.addStretch()
    manual_root.addLayout(filters)

    actions = QHBoxLayout()
    counter = QLabel("Выбрано: 0")
    copy_mode = QComboBox()
    copy_mode.addItems([
        "ФИО",
        "ФИО + должность",
        "ФИО + табельный №",
        "ФИО + должность + табельный №",
        "ФИО + телефон",
    ])
    copy_button = QPushButton("Копировать состав")
    clear_button = QPushButton("Очистить")
    create_button = QPushButton("Создать событие")
    create_button.setProperty("role", "primary")
    actions.addWidget(counter)
    actions.addStretch()
    actions.addWidget(copy_mode)
    actions.addWidget(copy_button)
    actions.addWidget(clear_button)
    actions.addWidget(create_button)
    manual_root.addLayout(actions)

    table = QTableWidget(0, 11)
    table.setHorizontalHeaderLabels([
        "✓", "ФИО", "Должность", "Подразделение", "Отделение", "Группа",
        "График", "Состояние", "Доступность", "Таб. №", "ID",
    ])
    table.setColumnHidden(10, True)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    header.setSectionResizeMode(2, QHeaderView.Stretch)
    manual_root.addWidget(table, 1)

    # -------------------- Semi-auto placeholder ---------------------------
    semi = QWidget()
    semi_root = QVBoxLayout(semi)
    semi_root.setContentsMargins(18, 18, 18, 18)
    semi_title = QLabel("Полуавтоматический подбор")
    semi_title.setObjectName("pageTitle")
    semi_text = QLabel(
        "Будет подключён на этапе v0.8.3-G. Программа предложит состав по "
        "выбранной дате и условиям, но окончательный выбор всегда останется за пользователем."
    )
    semi_text.setObjectName("secondaryText")
    semi_text.setWordWrap(True)
    semi_root.addWidget(semi_title)
    semi_root.addWidget(semi_text)
    semi_root.addStretch()
    mode_tabs.addTab(semi, "Полуавтоматический режим")

    window.manual_team_mode_tabs = mode_tabs
    window.manual_team_date = team_date
    window.manual_team_table = table
    window.manual_team_search = search
    window.manual_team_department = department
    window.manual_team_section = section
    window.manual_team_group = group
    window.manual_team_position = position
    window.manual_team_schedule = schedule
    window.manual_team_copy_mode = copy_mode

    selected: set[int] = set()
    candidate_cache: dict[int, dict[str, Any]] = {}

    def day_state_service():
        today_page = getattr(window, "today_page", None)
        return getattr(today_page, "day_state", None)

    def selected_iso() -> str:
        return team_date.date().toString("yyyy-MM-dd")

    def candidates() -> list[dict[str, Any]]:
        state_service = day_state_service()
        if state_service is None:
            return []
        snapshot = state_service.snapshot(selected_iso())
        result: list[dict[str, Any]] = []
        for row in snapshot.rows:
            details = window.service.get_employee(int(row.employee_id))
            if details is None:
                continue
            result.append({
                "employee_id": int(row.employee_id),
                "fio": row.fio,
                "personnel_no": row.personnel_no,
                "phone": str(details["phone"] or ""),
                "department": row.department,
                "section": row.section,
                "group": str(details["effective_group"] or details["group_name"] or "—"),
                "position": row.position,
                "schedule": str(details["schedule_type"] or "Не задан"),
                "status": row.status_text,
                "availability": row.availability,
            })
        return result

    def fill_combo(combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Все")
        for value in sorted({str(value or "").strip() for value in values}, key=str.casefold):
            if value and value != "—":
                combo.addItem(value)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def refresh_filter_values(rows: list[dict[str, Any]]) -> None:
        fill_combo(department, [row["department"] for row in rows])
        fill_combo(section, [row["section"] for row in rows])
        fill_combo(group, [row["group"] for row in rows])
        fill_combo(position, [row["position"] for row in rows])
        fill_combo(schedule, [row["schedule"] for row in rows])

    def matches(row: dict[str, Any]) -> bool:
        needle = search.text().strip().casefold()
        if needle and needle not in f"{row['fio']} {row['personnel_no']}".casefold():
            return False
        for combo, key in (
            (department, "department"),
            (section, "section"),
            (group, "group"),
            (position, "position"),
            (schedule, "schedule"),
        ):
            if combo.currentText() != "Все" and row[key] != combo.currentText():
                return False
        return True

    def update_actions() -> None:
        count = len(selected)
        counter.setText(f"Выбрано: {count}")
        copy_mode.setEnabled(count > 0)
        copy_button.setEnabled(count > 0)
        clear_button.setEnabled(count > 0)
        create_button.setEnabled(count >= 2)

    def rebuild_table(*_args) -> None:
        rows = list(candidate_cache.values())
        table.blockSignals(True)
        table.setRowCount(0)
        for row_data in rows:
            if not matches(row_data):
                continue
            row = table.rowCount()
            table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(
                Qt.Checked if row_data["employee_id"] in selected else Qt.Unchecked
            )
            check.setData(Qt.UserRole, row_data["employee_id"])
            table.setItem(row, 0, check)
            values = [
                row_data["fio"], row_data["position"] or "—",
                row_data["department"] or "—", row_data["section"] or "—",
                row_data["group"] or "—", row_data["schedule"] or "Не задан",
                row_data["status"] or "—", row_data["availability"] or "—",
                row_data["personnel_no"] or "—", row_data["employee_id"],
            ]
            for column, value in enumerate(values, 1):
                item = QTableWidgetItem(str(value))
                if column == 1:
                    item.setData(Qt.UserRole, row_data["employee_id"])
                table.setItem(row, column, item)
        table.blockSignals(False)
        update_actions()

    def refresh_candidates(*_args) -> None:
        try:
            rows = candidates()
        except ValueError as exc:
            QMessageBox.warning(team_tab, "Формирование команды", str(exc))
            rows = []
        candidate_cache.clear()
        candidate_cache.update({row["employee_id"]: row for row in rows})
        # Drop selections that no longer belong to the current listed staff.
        selected.intersection_update(candidate_cache.keys())
        refresh_filter_values(rows)
        rebuild_table()

    def item_changed(item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        employee_id = item.data(Qt.UserRole)
        if employee_id is None:
            return
        if item.checkState() == Qt.Checked:
            selected.add(int(employee_id))
        else:
            selected.discard(int(employee_id))
        update_actions()

    def toggle_row(row: int, _column: int) -> None:
        check = table.item(row, 0)
        if check is not None:
            check.setCheckState(
                Qt.Unchecked if check.checkState() == Qt.Checked else Qt.Checked
            )

    def clear_selection() -> None:
        selected.clear()
        rebuild_table()

    def copy_selection() -> None:
        if not selected:
            return
        mode = copy_mode.currentText()
        lines: list[str] = []
        for employee_id in sorted(selected, key=lambda value: candidate_cache.get(value, {}).get("fio", "").casefold()):
            row = candidate_cache.get(employee_id)
            if not row:
                continue
            fio = row["fio"]
            position_text = row["position"] or "—"
            number = row["personnel_no"] or "—"
            phone = row["phone"] or "—"
            if mode == "ФИО":
                line = fio
            elif mode == "ФИО + должность":
                line = f"{fio} — {position_text}"
            elif mode == "ФИО + табельный №":
                line = f"{fio} — таб. № {number}"
            elif mode == "ФИО + должность + табельный №":
                line = f"{fio} — {position_text} — таб. № {number}"
            else:
                line = f"{fio} — {phone}"
            lines.append(line)
        QApplication.clipboard().setText("\n".join(lines))

    def create_event() -> None:
        ids = sorted(selected)
        if len(ids) < 2:
            QMessageBox.information(
                team_tab,
                "Создать событие",
                "Для группового события выберите не менее двух работников.",
            )
            return
        from ui import BatchEventDialog
        dialog = BatchEventDialog(window.service, window, preselected=ids)
        chosen = team_date.date()
        dialog.start.setDate(chosen)
        dialog.end.setDate(chosen)
        if dialog.exec():
            window.refresh_all()

    window.refresh_manual_team = refresh_candidates
    window.copy_manual_team = copy_selection
    window.create_manual_team_event = create_event
    window.manual_team_selected_ids = lambda: sorted(selected)

    table.itemChanged.connect(item_changed)
    table.cellDoubleClicked.connect(toggle_row)
    team_date.dateChanged.connect(refresh_candidates)
    search.textChanged.connect(rebuild_table)
    for combo in (department, section, group, position, schedule):
        combo.currentTextChanged.connect(rebuild_table)
    copy_button.clicked.connect(copy_selection)
    clear_button.clicked.connect(clear_selection)
    create_button.clicked.connect(create_event)
    mode_tabs.currentChanged.connect(lambda index: refresh_candidates() if index == 0 else None)

    # Entering from Today carries the exact day the user was looking at.
    if hasattr(window, "today_page") and hasattr(window.today_page, "team"):
        try:
            window.today_page.team.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass

        def open_from_today() -> None:
            team_date.setDate(window.today_page.selected_date)
            tabs.setCurrentIndex(1)
            mode_tabs.setCurrentIndex(0)
            refresh_candidates()
            window._select_page(0)

        window.today_page.team.clicked.connect(open_from_today)

    # Keep the candidate list in sync with employee/event/staff changes while
    # preserving every existing refresh wrapper installed before this stage.
    original_refresh_all = window.refresh_all

    def refresh_all() -> None:
        original_refresh_all()
        refresh_candidates()

    window.refresh_all = refresh_all
    refresh_candidates()
    window._manual_team_ui_installed = True
