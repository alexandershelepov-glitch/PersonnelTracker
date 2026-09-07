"""Semi-automatic team proposal UI for PersonnelTracker v0.8.3-G."""
from __future__ import annotations

from typing import Any

from config import SCHEDULE_TYPES
from team_selection import SemiAutoTeamService, TeamCandidate


def install_semi_auto_team_ui(window: Any) -> None:
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDateEdit,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    if getattr(window, "_semi_auto_team_ui_installed", False):
        return
    mode_tabs = getattr(window, "manual_team_mode_tabs", None)
    if mode_tabs is None or mode_tabs.count() < 2:
        return

    old = mode_tabs.widget(1)
    semi = QWidget()
    mode_tabs.removeTab(1)
    mode_tabs.insertTab(1, semi, "Полуавтоматический режим")
    if old is not None:
        old.setParent(None)
        old.deleteLater()

    root = QVBoxLayout(semi)
    root.setContentsMargins(8, 10, 8, 8)
    root.setSpacing(10)

    intro = QLabel(
        "Программа только предлагает состав. Существующие события на выбранный день "
        "исключаются, график учитывается как приоритет, а равномерность считается по "
        "предыдущим групповым назначениям. Перед созданием состав можно свободно изменить."
    )
    intro.setObjectName("secondaryText")
    intro.setWordWrap(True)
    root.addWidget(intro)

    top = QHBoxLayout()
    team_date = QDateEdit()
    team_date.setCalendarPopup(True)
    team_date.setDisplayFormat("dd.MM.yyyy")
    team_date.setDate(getattr(window, "manual_team_date", None).date() if hasattr(window, "manual_team_date") else QDate.currentDate())
    desired = QSpinBox()
    desired.setRange(2, 200)
    desired.setValue(2)
    lookback = QSpinBox()
    lookback.setRange(1, 365)
    lookback.setValue(30)
    lookback.setSuffix(" дн.")
    top.addWidget(QLabel("Дата:"))
    top.addWidget(team_date)
    top.addWidget(QLabel("Нужно человек:"))
    top.addWidget(desired)
    top.addWidget(QLabel("Равномерность за:"))
    top.addWidget(lookback)
    top.addStretch()
    root.addLayout(top)

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
    root.addLayout(filters)

    options = QHBoxLayout()
    include_off = QCheckBox("Разрешать выходной по графику")
    include_check = QCheckBox("Включать «Требует проверки»")
    require_weapon = QCheckBox("Только с закреплённым оружием")
    options.addWidget(include_off)
    options.addWidget(include_check)
    options.addWidget(require_weapon)
    options.addStretch()
    root.addLayout(options)

    actions = QHBoxLayout()
    status = QLabel("Нажмите «Предложить состав»")
    status.setObjectName("secondaryText")
    propose_button = QPushButton("Предложить состав")
    propose_button.setProperty("role", "primary")
    replace_button = QPushButton("Заменить выбранного")
    copy_button = QPushButton("Копировать состав")
    clear_button = QPushButton("Очистить")
    create_button = QPushButton("Создать событие")
    actions.addWidget(status, 1)
    actions.addWidget(propose_button)
    actions.addWidget(replace_button)
    actions.addWidget(copy_button)
    actions.addWidget(clear_button)
    actions.addWidget(create_button)
    root.addLayout(actions)

    table = QTableWidget(0, 10)
    table.setHorizontalHeaderLabels([
        "✓", "ФИО", "Должность", "Подразделение / отделение", "График",
        "Состояние", "Привлечений", "Последнее", "Почему предложен", "ID",
    ])
    table.setColumnHidden(9, True)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    header.setSectionResizeMode(2, QHeaderView.Stretch)
    header.setSectionResizeMode(8, QHeaderView.Stretch)
    root.addWidget(table, 1)

    day_state = getattr(getattr(window, "today_page", None), "day_state", None)
    if day_state is None:
        return
    selector = SemiAutoTeamService(window.service, day_state)
    candidate_cache: list[TeamCandidate] = []
    selected: set[int] = set()

    window.semi_auto_team_date = team_date
    window.semi_auto_team_desired = desired
    window.semi_auto_team_lookback = lookback
    window.semi_auto_team_table = table
    window.semi_auto_team_department = department
    window.semi_auto_team_section = section
    window.semi_auto_team_group = group
    window.semi_auto_team_position = position
    window.semi_auto_team_schedule = schedule
    window.semi_auto_team_include_off = include_off
    window.semi_auto_team_include_check = include_check
    window.semi_auto_team_require_weapon = require_weapon

    def fill_combo(combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Все")
        seen: set[str] = set()
        for value in values:
            clean = str(value or "").strip()
            key = clean.casefold()
            if not clean or clean == "—" or key in seen:
                continue
            seen.add(key)
            combo.addItem(clean)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def refresh_filter_values() -> None:
        fill_combo(department, window.service.unique_field_values("department"))
        fill_combo(section, window.service.unique_field_values("section"))
        fill_combo(group, window.service.unique_field_values("group_name"))
        fill_combo(position, window.service.unique_field_values("position"))
        fill_combo(schedule, SCHEDULE_TYPES)

    def selected_iso() -> str:
        return team_date.date().toString("yyyy-MM-dd")

    def rebuild_table() -> None:
        table.blockSignals(True)
        table.setRowCount(len(candidate_cache))
        for row, candidate in enumerate(candidate_cache):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if candidate.employee_id in selected else Qt.Unchecked)
            check.setData(Qt.UserRole, candidate.employee_id)
            table.setItem(row, 0, check)
            organisation = " / ".join(
                value for value in (candidate.department, candidate.section)
                if value and value != "—"
            ) or "—"
            last = "—"
            if candidate.last_participation:
                parsed = QDate.fromString(candidate.last_participation, "yyyy-MM-dd")
                last = parsed.toString("dd.MM.yyyy") if parsed.isValid() else candidate.last_participation
            values = [
                candidate.fio,
                candidate.position or "—",
                organisation,
                candidate.schedule_type or "Не задан",
                candidate.day_status or "—",
                candidate.participation_count,
                last,
                candidate.reason,
                candidate.employee_id,
            ]
            for column, value in enumerate(values, 1):
                item = QTableWidgetItem(str(value))
                if column == 1:
                    item.setData(Qt.UserRole, candidate.employee_id)
                table.setItem(row, column, item)
            table.setRowHeight(row, 32)
        table.blockSignals(False)
        update_actions()

    def refresh_pool(*_args, clear_selection: bool = True) -> None:
        nonlocal candidate_cache
        if clear_selection:
            selected.clear()
        try:
            candidate_cache = selector.candidates(
                selected_iso(),
                lookback_days=lookback.value(),
                department=department.currentText(),
                section=section.currentText(),
                group_name=group.currentText(),
                position=position.currentText(),
                schedule_type=schedule.currentText(),
                include_schedule_off=include_off.isChecked(),
                include_needs_check=include_check.isChecked(),
                require_weapon=require_weapon.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(semi, "Подбор команды", str(exc))
            candidate_cache = []
        rebuild_table()
        status.setText(f"Подходящих кандидатов: {len(candidate_cache)}")

    def update_actions() -> None:
        count = len(selected)
        create_button.setEnabled(count >= 2)
        copy_button.setEnabled(count > 0)
        clear_button.setEnabled(count > 0)
        replace_button.setEnabled(count > 0 and len(candidate_cache) > count)
        if count:
            status.setText(f"Выбрано: {count} из {desired.value()} • кандидатов: {len(candidate_cache)}")

    def propose() -> None:
        selected.clear()
        selected.update(selector.propose(candidate_cache, desired.value()))
        rebuild_table()
        if len(candidate_cache) < desired.value():
            status.setText(
                f"Доступно только {len(candidate_cache)} кандидатов из требуемых {desired.value()}. "
                "Измените условия или скорректируйте состав вручную."
            )
        else:
            status.setText(f"Предложено: {len(selected)}. Состав можно изменить вручную.")

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

    def replace_current() -> None:
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(semi, "Замена", "Выберите строку работника, которого нужно заменить.")
            return
        current = table.item(row, 9)
        if current is None:
            return
        employee_id = int(current.text())
        if employee_id not in selected:
            QMessageBox.information(semi, "Замена", "Сначала отметьте этого работника в составе.")
            return
        replacement = next((item.employee_id for item in candidate_cache if item.employee_id not in selected), None)
        if replacement is None:
            QMessageBox.information(semi, "Замена", "Других подходящих кандидатов нет.")
            return
        selected.discard(employee_id)
        selected.add(replacement)
        rebuild_table()

    def clear_selection() -> None:
        selected.clear()
        rebuild_table()
        status.setText(f"Подходящих кандидатов: {len(candidate_cache)}")

    def copy_selection() -> None:
        by_id = {item.employee_id: item for item in candidate_cache}
        lines = []
        for employee_id in sorted(selected, key=lambda value: by_id[value].fio.casefold() if value in by_id else ""):
            candidate = by_id.get(employee_id)
            if candidate:
                lines.append(
                    f"{candidate.fio} — {candidate.position or '—'} — таб. № {candidate.personnel_no or '—'}"
                )
        QApplication.clipboard().setText("\n".join(lines))

    def create_event() -> None:
        ids = sorted(selected)
        if len(ids) < 2:
            return
        from ui import BatchEventDialog
        dialog = BatchEventDialog(window.service, window, preselected=ids)
        chosen = team_date.date()
        dialog.start.setDate(chosen)
        dialog.end.setDate(chosen)
        if dialog.exec():
            window.refresh_all()
            refresh_pool(clear_selection=True)

    window.refresh_semi_auto_team = refresh_pool
    window.propose_semi_auto_team = propose
    window.semi_auto_team_selected_ids = lambda: sorted(selected)
    window.create_semi_auto_team_event = create_event

    table.itemChanged.connect(item_changed)
    propose_button.clicked.connect(propose)
    replace_button.clicked.connect(replace_current)
    copy_button.clicked.connect(copy_selection)
    clear_button.clicked.connect(clear_selection)
    create_button.clicked.connect(create_event)

    for control in (team_date, desired, lookback):
        if isinstance(control, QDateEdit):
            control.dateChanged.connect(lambda _value: refresh_pool(clear_selection=True))
        else:
            control.valueChanged.connect(lambda _value: refresh_pool(clear_selection=True))
    for combo in (department, section, group, position, schedule):
        combo.currentTextChanged.connect(lambda _text: refresh_pool(clear_selection=True))
    for checkbox in (include_off, include_check, require_weapon):
        checkbox.toggled.connect(lambda _checked: refresh_pool(clear_selection=True))

    def mode_changed(index: int) -> None:
        if index != 1:
            return
        if hasattr(window, "manual_team_date"):
            team_date.setDate(window.manual_team_date.date())
        refresh_filter_values()
        refresh_pool(clear_selection=True)

    mode_tabs.currentChanged.connect(mode_changed)

    original_refresh_all = window.refresh_all
    def refresh_all() -> None:
        original_refresh_all()
        refresh_filter_values()
        if mode_tabs.currentIndex() == 1:
            refresh_pool(clear_selection=False)
    window.refresh_all = refresh_all

    refresh_filter_values()
    refresh_pool(clear_selection=True)
    window._semi_auto_team_ui_installed = True
