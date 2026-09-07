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
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLayout,
        QMessageBox,
        QPushButton,
        QScrollArea,
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
    semi = QScrollArea()
    semi.setWidgetResizable(True)
    semi.setFrameShape(QFrame.NoFrame)
    semi_body = QWidget()
    semi.setWidget(semi_body)
    mode_tabs.removeTab(1)
    mode_tabs.insertTab(1, semi, "Полуавтоматический режим")
    if old is not None:
        old.setParent(None)
        old.deleteLater()

    root = QVBoxLayout(semi_body)
    root.setContentsMargins(8, 10, 8, 8)
    root.setSpacing(10)
    root.setSizeConstraint(QLayout.SetMinimumSize)

    intro = QLabel(
        "Программа только предлагает состав. Существующие события на выбранный день "
        "исключаются, график учитывается как приоритет, а равномерность считается по "
        "предыдущим групповым назначениям. Перед созданием состав можно свободно изменить."
    )
    intro.setObjectName("secondaryText")
    intro.setWordWrap(True)
    root.addWidget(intro)

    top = QGridLayout()
    team_date = QDateEdit()
    team_date.setCalendarPopup(True)
    team_date.setDisplayFormat("dd.MM.yyyy")
    team_date.setDate(
        getattr(window, "manual_team_date", None).date()
        if hasattr(window, "manual_team_date")
        else QDate.currentDate()
    )
    desired = QSpinBox()
    desired.setRange(2, 200)
    desired.setValue(2)
    lookback = QSpinBox()
    lookback.setRange(1, 365)
    lookback.setValue(30)
    lookback.setSuffix(" дн.")
    top.addWidget(QLabel("Дата:"), 0, 0)
    top.addWidget(team_date, 0, 1)
    top.addWidget(QLabel("Нужно человек:"), 0, 2)
    top.addWidget(desired, 0, 3)
    top.addWidget(QLabel("Равномерность за:"), 1, 0)
    top.addWidget(lookback, 1, 1)
    top.setColumnStretch(3, 1)
    root.addLayout(top)

    filters = QGridLayout()
    department = QComboBox()
    section = QComboBox()
    group = QComboBox()
    position = QComboBox()
    schedule = QComboBox()
    for index, (caption, combo) in enumerate((
        ("Подразделение:", department),
        ("Отделение:", section),
        ("Группа:", group),
        ("Должность:", position),
        ("График:", schedule),
    )):
        row, pair = divmod(index, 2)
        filters.addWidget(QLabel(caption), row, pair * 2)
        filters.addWidget(combo, row, pair * 2 + 1)
    filters.setColumnStretch(1, 1)
    filters.setColumnStretch(3, 1)
    filter_status = QLabel()
    filter_status.setObjectName("secondaryText")
    reset_filters = QPushButton("Сбросить фильтры")
    filters.addWidget(filter_status, 3, 0, 1, 2)
    filters.addWidget(reset_filters, 3, 3)
    root.addLayout(filters)

    options = QGridLayout()
    include_off = QCheckBox("Разрешать выходной по графику")
    include_check = QCheckBox("Включать «Требует проверки»")
    require_weapon = QCheckBox("Только с закреплённым оружием")
    options.addWidget(include_off, 0, 0)
    options.addWidget(include_check, 0, 1)
    options.addWidget(require_weapon, 1, 0, 1, 2)
    root.addLayout(options)

    actions = QGridLayout()
    status = QLabel("Нажмите «Предложить состав»")
    status.setObjectName("secondaryText")
    propose_button = QPushButton("Предложить состав")
    propose_button.setProperty("role", "primary")
    replace_button = QPushButton("Заменить выбранного")
    copy_button = QPushButton("Копировать состав")
    clear_button = QPushButton("Очистить")
    create_button = QPushButton("Создать событие")
    actions.addWidget(status, 0, 0, 1, 3)
    actions.addWidget(propose_button, 1, 0)
    actions.addWidget(replace_button, 1, 1)
    actions.addWidget(copy_button, 1, 2)
    actions.addWidget(clear_button, 2, 1)
    actions.addWidget(create_button, 2, 2)
    actions.setColumnStretch(0, 1)
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
    table.setMinimumHeight(220)
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
    window.semi_auto_team_filter_status = filter_status
    window.semi_auto_team_reset_filters = reset_filters

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

    def filters_active() -> bool:
        return any(
            combo.currentText() != "Все"
            for combo in (department, section, group, position, schedule)
        ) or any(
            checkbox.isChecked()
            for checkbox in (include_off, include_check, require_weapon)
        )

    def update_filter_status() -> None:
        active = filters_active()
        filter_status.setText("Фильтры применены" if active else "")
        reset_filters.setEnabled(active)

    def clear_filters() -> None:
        for combo in (department, section, group, position, schedule):
            combo.setCurrentIndex(0)
        for checkbox in (include_off, include_check, require_weapon):
            checkbox.setChecked(False)
        update_filter_status()

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
                last = (
                    parsed.toString("dd.MM.yyyy")
                    if parsed.isValid()
                    else candidate.last_participation
                )
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
                item.setToolTip(str(value))
                table.setItem(row, column, item)
            table.setRowHeight(row, 32)
        table.blockSignals(False)
        table.setVisible(bool(candidate_cache))
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
        eligible_ids = {candidate.employee_id for candidate in candidate_cache}
        selected.intersection_update(eligible_ids)
        rebuild_table()
        if not selected:
            status.setText(
                f"Подходящих кандидатов: {len(candidate_cache)}"
                if candidate_cache
                else "По заданным условиям сотрудники не найдены"
            )
        update_filter_status()

    def update_actions() -> None:
        count = len(selected)
        create_button.setEnabled(count >= 2)
        copy_button.setEnabled(count > 0)
        clear_button.setEnabled(count > 0)
        replace_button.setEnabled(count > 0 and len(candidate_cache) > count)
        if count:
            status.setText(
                f"Выбрано: {count} из {desired.value()} • кандидатов: {len(candidate_cache)}"
            )

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
            status.setText(
                f"Предложено: {len(selected)}. Состав можно изменить вручную."
            )

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
            QMessageBox.information(
                semi, "Замена", "Выберите строку работника, которого нужно заменить."
            )
            return
        current = table.item(row, 9)
        if current is None:
            return
        employee_id = int(current.text())
        if employee_id not in selected:
            QMessageBox.information(
                semi, "Замена", "Сначала отметьте этого работника в составе."
            )
            return
        replacement = next(
            (
                item.employee_id
                for item in candidate_cache
                if item.employee_id not in selected
            ),
            None,
        )
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
        for employee_id in sorted(
            selected,
            key=lambda value: by_id[value].fio.casefold() if value in by_id else "",
        ):
            candidate = by_id.get(employee_id)
            if candidate:
                lines.append(
                    f"{candidate.fio} — {candidate.position or '—'} — "
                    f"таб. № {candidate.personnel_no or '—'}"
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
    reset_filters.clicked.connect(clear_filters)

    team_date.dateChanged.connect(lambda _value: refresh_pool(clear_selection=True))
    lookback.valueChanged.connect(lambda _value: refresh_pool(clear_selection=True))
    # Desired size changes the requested proposal size, not candidate validity;
    # keep any manual corrections until the user explicitly proposes again.
    desired.valueChanged.connect(lambda _value: update_actions())
    for combo in (department, section, group, position, schedule):
        combo.currentTextChanged.connect(
            lambda _text: refresh_pool(clear_selection=True)
        )
    for checkbox in (include_off, include_check, require_weapon):
        checkbox.toggled.connect(
            lambda _checked: refresh_pool(clear_selection=True)
        )

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
