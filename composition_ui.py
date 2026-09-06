"""Composition workspace for PersonnelTracker v0.8.3-C.

The module reorganises the existing staff screen around three user-facing
workflows without replacing the underlying staff-unit or employee services:
Directory, Team formation (container only at this stage), and the existing
SHDS screen.
"""
from __future__ import annotations

from typing import Any


def install_composition_ui(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFrame,
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

    if getattr(window, "_composition_ui_installed", False):
        return

    page = window.pages.widget(0)
    root = page.layout() if page is not None else None
    if root is None:
        return

    # Keep the page title in place and move every existing SHDS control into a
    # dedicated tab. These are the original widgets, signals and handlers — no
    # second staff-unit implementation is introduced.
    for label in page.findChildren(QLabel):
        if label.objectName() == "pageTitle":
            label.setText("Состав")
            break

    shds_tab = QWidget()
    shds_root = QVBoxLayout(shds_tab)
    shds_root.setContentsMargins(0, 6, 0, 0)
    shds_root.setSpacing(10)

    # The v0.8.3-A compatibility button is no longer needed because employees
    # are now directly available in the Directory tab.
    while root.count() > 1:
        item = root.takeAt(1)
        widget = item.widget()
        child_layout = item.layout()
        spacer = item.spacerItem()
        if widget is not None:
            if isinstance(widget, QPushButton) and widget.text() == "Открыть работников":
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            else:
                shds_root.addWidget(widget)
        elif child_layout is not None:
            shds_root.addLayout(child_layout)
        elif spacer is not None:
            shds_root.addItem(spacer)

    tabs = QTabWidget()
    tabs.setObjectName("compositionTabs")
    window.composition_tabs = tabs

    # -------------------- Directory ---------------------------------------
    directory = QWidget()
    directory_root = QVBoxLayout(directory)
    directory_root.setContentsMargins(0, 8, 0, 0)
    directory_root.setSpacing(10)

    intro = QLabel(
        "Быстрый справочник работников: найдите людей, отфильтруйте состав, "
        "выделите нужных и скопируйте сведения в один клик."
    )
    intro.setObjectName("secondaryText")
    intro.setWordWrap(True)
    directory_root.addWidget(intro)

    search_row = QHBoxLayout()
    search = QLineEdit()
    search.setPlaceholderText("ФИО, табельный номер, телефон, должность...")
    search_row.addWidget(QLabel("Поиск:"))
    search_row.addWidget(search, 1)
    active_only = QCheckBox("Только действующие")
    active_only.setChecked(True)
    search_row.addWidget(active_only)
    directory_root.addLayout(search_row)

    filters = QHBoxLayout()
    department = QComboBox()
    section = QComboBox()
    group = QComboBox()
    position = QComboBox()
    for caption, combo in (
        ("Подразделение:", department),
        ("Отделение:", section),
        ("Группа:", group),
        ("Должность:", position),
    ):
        combo.setMinimumWidth(120)
        filters.addWidget(QLabel(caption))
        filters.addWidget(combo)
    filters.addStretch()
    directory_root.addLayout(filters)

    actions = QHBoxLayout()
    selected_label = QLabel("Выбрано: 0")
    copy_mode = QComboBox()
    copy_mode.addItems([
        "ФИО",
        "ФИО + должность",
        "ФИО + табельный №",
        "ФИО + должность + табельный №",
        "ФИО + телефон",
    ])
    copy_button = QPushButton("Копировать")
    copy_button.setProperty("role", "primary")
    open_button = QPushButton("Открыть карточку")
    copy_mode.setEnabled(False)
    copy_button.setEnabled(False)
    open_button.setEnabled(False)
    actions.addWidget(selected_label)
    actions.addStretch()
    actions.addWidget(copy_mode)
    actions.addWidget(copy_button)
    actions.addWidget(open_button)
    directory_root.addLayout(actions)

    table = QTableWidget(0, 7)
    table.setObjectName("compositionDirectory")
    table.setHorizontalHeaderLabels([
        "ФИО", "Должность", "Таб. №", "Телефон", "Подразделение", "График", "ID",
    ])
    table.setColumnHidden(6, True)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.ExtendedSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(0, QHeaderView.Stretch)
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    directory_root.addWidget(table, 1)

    # Expose widgets for lightweight UI tests and future team-builder reuse.
    window.composition_directory = directory
    window.composition_directory_table = table
    window.composition_search = search
    window.composition_department = department
    window.composition_section = section
    window.composition_group = group
    window.composition_position = position
    window.composition_active_only = active_only
    window.composition_copy_mode = copy_mode

    def fill_combo(combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Все")
        for value in values:
            clean = (value or "").strip()
            if clean and clean != "—":
                combo.addItem(clean)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def refresh_filter_values() -> None:
        service = window.service
        fill_combo(department, service.unique_field_values("department"))
        fill_combo(section, service.unique_field_values("section"))
        fill_combo(group, service.unique_field_values("group_name"))
        fill_combo(position, service.unique_field_values("position"))

    def effective_person(person):
        details = window.service.get_employee(int(person["id"]))
        return details or person

    def refresh_directory(*_args) -> None:
        needle = search.text().strip().casefold()
        people = window.service.list_employees(
            include_archived=not active_only.isChecked()
        )
        rows = []
        for person in people:
            details = effective_person(person)
            dep = str(details["effective_department"] or details["department"] or "")
            sec = str(details["effective_section"] or details["section"] or "")
            grp = str(details["effective_group"] or details["group_name"] or "")
            pos = str(details["effective_position"] or details["position"] or "")
            phone = str(details["phone"] or "")
            number = str(details["personnel_no"] or "")
            haystack = " ".join((str(details["fio"] or ""), number, phone, dep, sec, grp, pos)).casefold()
            if needle and needle not in haystack:
                continue
            if department.currentText() != "Все" and dep != department.currentText():
                continue
            if section.currentText() != "Все" and sec != section.currentText():
                continue
            if group.currentText() != "Все" and grp != group.currentText():
                continue
            if position.currentText() != "Все" and pos != position.currentText():
                continue
            organisation = " / ".join(value for value in (dep, sec) if value and value != "—") or "—"
            rows.append((details, pos or "—", phone or "—", number or "—", organisation))

        table.setRowCount(len(rows))
        for row_index, (details, pos, phone, number, organisation) in enumerate(rows):
            values = [
                details["fio"] or "—",
                pos,
                number,
                phone,
                organisation,
                details["schedule_type"] or "Не задан",
                int(details["id"]),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, int(details["id"]))
                    item.setToolTip(
                        f"{details['employment_status'] or 'Работает'} · "
                        f"{details['effective_group'] or 'группа не указана'}"
                    )
                table.setItem(row_index, column, item)
        update_selected_count()

    def selected_ids() -> list[int]:
        ids: list[int] = []
        for row in sorted({index.row() for index in table.selectedIndexes()}):
            item = table.item(row, 0)
            employee_id = item.data(Qt.UserRole) if item is not None else None
            if employee_id is not None:
                ids.append(int(employee_id))
        return ids

    def update_selected_count() -> None:
        count = len(selected_ids())
        selected_label.setText(f"Выбрано: {count}")
        copy_mode.setEnabled(count > 0)
        copy_button.setEnabled(count > 0)
        open_button.setEnabled(count > 0)

    def open_employee(employee_id: int) -> None:
        from ui import EmployeeDialog
        dialog = EmployeeDialog(window.service, employee_id, window)
        # The profile redesign belongs to v0.8.3-D. For now preserve the
        # working card but make returning to Composition explicit.
        for button in dialog.findChildren(QPushButton):
            if button.text() in {"Закрыть", "Отмена"}:
                button.setText("← Назад")
        dialog.exec()
        window.refresh_all()

    def open_selected() -> None:
        ids = selected_ids()
        if not ids:
            QMessageBox.information(directory, "Справочник", "Сначала выберите работника.")
            return
        open_employee(ids[0])

    def copy_selected() -> None:
        ids = selected_ids()
        if not ids:
            QMessageBox.information(directory, "Копирование", "Выберите одного или нескольких работников.")
            return
        mode = copy_mode.currentText()
        lines: list[str] = []
        for employee_id in ids:
            person = window.service.get_employee(employee_id)
            if not person:
                continue
            fio = str(person["fio"] or "")
            pos = str(person["effective_position"] or person["position"] or "—")
            number = str(person["personnel_no"] or "—")
            phone = str(person["phone"] or "—")
            if mode == "ФИО":
                line = fio
            elif mode == "ФИО + должность":
                line = f"{fio} — {pos}"
            elif mode == "ФИО + табельный №":
                line = f"{fio} — таб. № {number}"
            elif mode == "ФИО + должность + табельный №":
                line = f"{fio} — {pos} — таб. № {number}"
            else:
                line = f"{fio} — {phone}"
            lines.append(line)
        QApplication.clipboard().setText("\n".join(lines))

    window.refresh_composition_directory = refresh_directory
    window.copy_composition_selection = copy_selected

    refresh_filter_values()
    for control in (search, active_only, department, section, group, position):
        if isinstance(control, QLineEdit):
            control.textChanged.connect(refresh_directory)
        elif isinstance(control, QCheckBox):
            control.toggled.connect(refresh_directory)
        else:
            control.currentTextChanged.connect(refresh_directory)
    table.itemSelectionChanged.connect(update_selected_count)
    table.doubleClicked.connect(lambda _index: open_selected())
    open_button.clicked.connect(open_selected)
    copy_button.clicked.connect(copy_selected)
    refresh_directory()

    # -------------------- Team container -----------------------------------
    team_tab = QWidget()
    team_root = QVBoxLayout(team_tab)
    team_root.setContentsMargins(8, 14, 8, 8)
    team_root.setSpacing(14)
    team_title = QLabel("Сформировать команду")
    team_title.setObjectName("pageTitle")
    team_root.addWidget(team_title)
    team_hint = QLabel(
        "Раздел подготовлен для следующих этапов: ручной выбор команды и "
        "полуавтоматическое предложение состава по выбранной дате."
    )
    team_hint.setObjectName("secondaryText")
    team_hint.setWordWrap(True)
    team_root.addWidget(team_hint)

    modes = QHBoxLayout()
    for caption, description in (
        ("Ручной режим", "Выбрать дату, отфильтровать доступных работников и отметить нужных вручную."),
        ("Полуавтоматический режим", "Задать количество и условия, получить предложение и скорректировать его перед подтверждением."),
    ):
        card = QFrame()
        card.setObjectName("metricCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        heading = QLabel(caption)
        heading.setStyleSheet("font-weight: 600;")
        text = QLabel(description)
        text.setWordWrap(True)
        text.setObjectName("secondaryText")
        card_layout.addWidget(heading)
        card_layout.addWidget(text)
        card_layout.addStretch()
        modes.addWidget(card, 1)
    team_root.addLayout(modes)
    status = QLabel("Логика формирования команды будет подключена отдельными этапами v0.8.3-F и v0.8.3-G.")
    status.setObjectName("secondaryText")
    status.setWordWrap(True)
    team_root.addWidget(status)
    team_root.addStretch()
    window.composition_team_tab = team_tab

    tabs.addTab(directory, "Справочник")
    tabs.addTab(team_tab, "Сформировать команду")
    tabs.addTab(shds_tab, "ШДС")
    root.addWidget(tabs, 1)

    # Entering Composition from the sidebar always means the ordinary
    # Directory. Contextual quick action from Today goes straight to Team.
    composition_button = window.nav_group.button(0)
    if composition_button is not None:
        composition_button.clicked.connect(lambda _checked=False: tabs.setCurrentIndex(0))

    if hasattr(window, "today_page") and hasattr(window.today_page, "team"):
        try:
            window.today_page.team.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass

        def open_team_from_today() -> None:
            tabs.setCurrentIndex(1)
            window._select_page(0)

        window.today_page.team.clicked.connect(open_team_from_today)

    # Refresh the new directory whenever existing application actions refresh
    # the shared data model (employee edit, import, restore, staff assignment).
    original_refresh = window.refresh_all

    def refresh_all() -> None:
        original_refresh()
        refresh_filter_values()
        refresh_directory()

    window.refresh_all = refresh_all
    window._composition_ui_installed = True
