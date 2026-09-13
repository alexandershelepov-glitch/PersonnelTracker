"""v1.1 user-customizable workspace preferences.

Presentation only. Preferences are stored in QSettings and never modify
personnel data, assignment history or database schema.
"""
from __future__ import annotations

from typing import Any


def _view_menu(window: Any):
    from PySide6.QtWidgets import QMenu

    # Workspace resets grouped by workspace_resize_ui into one submenu.
    grouped = getattr(window, "view_reset_menu", None)
    if isinstance(grouped, QMenu):
        return grouped
    for menu_action in window.menuBar().actions():
        menu = menu_action.menu()
        if isinstance(menu, QMenu) and menu.title() == "Вид":
            return menu
    return window.menuBar().addMenu("Вид")


def _install_shds_columns(window: Any) -> None:
    """Own SHDS column order/width/visibility as the single v1.1 authority."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QHeaderView

    table = getattr(window, "staff_table", None)
    if table is None:
        return

    shds_header = table.horizontalHeader()
    shds_header.setStretchLastSection(False)
    shds_header.setSectionsMovable(True)
    shds_header.setMinimumSectionSize(72)
    # ui.py leaves Должность/ФИО on Stretch. Restore uniform Interactive here so
    # every divider is draggable and this layer is the only geometry writer.
    for column in range(table.columnCount()):
        shds_header.setSectionResizeMode(column, QHeaderView.Interactive)

    settings_key = "workspace/shds_header_state"
    default_widths = tuple(table.columnWidth(column) for column in range(table.columnCount()))
    default_hidden = tuple(table.isColumnHidden(column) for column in range(table.columnCount()))

    def apply_shds_defaults() -> None:
        previous_block = shds_header.blockSignals(True)
        try:
            for logical in range(shds_header.count()):
                visual = shds_header.visualIndex(logical)
                if visual >= 0 and visual != logical:
                    shds_header.moveSection(visual, logical)

            for column, width in enumerate(default_widths):
                if column < table.columnCount():
                    table.setColumnWidth(column, width)
            for column, hidden in enumerate(default_hidden):
                if column < table.columnCount():
                    table.setColumnHidden(column, hidden)
        finally:
            shds_header.blockSignals(previous_block)

    saved_state = window.settings.value(settings_key)
    if saved_state:
        previous_block = shds_header.blockSignals(True)
        try:
            restored = shds_header.restoreState(saved_state)
        finally:
            shds_header.blockSignals(previous_block)
        if not restored:
            apply_shds_defaults()
        else:
            # Application-hidden columns are implementation details and must
            # not reappear because of stale saved state.
            for column, hidden in enumerate(default_hidden):
                if hidden and column < table.columnCount():
                    table.setColumnHidden(column, True)

    def save_shds_header(*_args) -> None:
        window.settings.setValue(settings_key, shds_header.saveState())

    def reset_shds_header() -> None:
        apply_shds_defaults()
        window.settings.remove(settings_key)

    shds_header.sectionMoved.connect(save_shds_header)
    shds_header.sectionResized.connect(save_shds_header)

    reset_action = QAction("Сбросить колонки ШДС", window)
    reset_action.triggered.connect(reset_shds_header)
    _view_menu(window).addAction(reset_action)

    window.shds_custom_header = shds_header
    window.shds_default_widths = default_widths
    window.shds_default_hidden = default_hidden
    window.reset_shds_columns = reset_shds_header
    window.reset_shds_columns_action = reset_action


def _install_today_tables(window: Any) -> None:
    """Keep Today operational tables user-resizable across every refresh."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QHeaderView

    today = getattr(window, "today_page", None)
    if today is None:
        return

    absent = getattr(today, "absent_table", None)
    shift = getattr(today, "shift_table", None)
    if absent is None or shift is None:
        return

    specs = (
        ("absent", absent, "today/absent_header_state"),
        ("shift", shift, "today/shift_header_state"),
    )

    def configure_table(table) -> None:
        # Grid colour and boundaries are owned by the shared theme; Today only
        # declares that it is a gridded data table.
        table.setShowGrid(True)
        table.setGridStyle(Qt.SolidLine)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setMinimumSectionSize(72)
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.Interactive)

    default_states: dict[str, Any] = {}
    headers: dict[str, Any] = {}

    for name, table, settings_key in specs:
        configure_table(table)
        header = table.horizontalHeader()
        headers[name] = header
        default_states[name] = header.saveState()

        saved = window.settings.value(settings_key)
        if saved:
            previous_block = header.blockSignals(True)
            try:
                restored = header.restoreState(saved)
                configure_table(table)
            finally:
                header.blockSignals(previous_block)
            if not restored:
                previous_block = header.blockSignals(True)
                try:
                    header.restoreState(default_states[name])
                    configure_table(table)
                finally:
                    header.blockSignals(previous_block)

        def save_header(*_args, _header=header, _key=settings_key) -> None:
            window.settings.setValue(_key, _header.saveState())

        header.sectionMoved.connect(save_header)
        header.sectionResized.connect(save_header)
        header.sectionDoubleClicked.connect(table.resizeColumnToContents)

    def reset_today_tables() -> None:
        for name, table, settings_key in specs:
            header = headers[name]
            previous_block = header.blockSignals(True)
            try:
                header.restoreState(default_states[name])
                configure_table(table)
                for logical in range(header.count()):
                    visual = header.visualIndex(logical)
                    if visual >= 0 and visual != logical:
                        header.moveSection(visual, logical)
            finally:
                header.blockSignals(previous_block)
            window.settings.remove(settings_key)

    reset_action = QAction("Сбросить колонки Сегодня", window)
    reset_action.triggered.connect(reset_today_tables)
    _view_menu(window).addAction(reset_action)

    window.today_absent_header = headers["absent"]
    window.today_shift_header = headers["shift"]
    window.today_absent_default_header_state = default_states["absent"]
    window.today_shift_default_header_state = default_states["shift"]
    window.reset_today_columns = reset_today_tables
    window.reset_today_columns_action = reset_action


def _install_composition_tab_order(window: Any) -> None:
    """Make Composition tabs directly draggable and persist their order."""
    import json

    from PySide6.QtGui import QAction

    tabs = getattr(window, "composition_tabs", None)
    directory = getattr(window, "composition_directory", None)
    team = getattr(window, "composition_team_tab", None)
    if tabs is None or directory is None or team is None or tabs.count() < 3:
        return

    # SHDS is the remaining Composition page. Identify it by widget identity,
    # not by translated tab text, so saved preferences stay stable if labels
    # change later.
    shds = next(
        (
            tabs.widget(index)
            for index in range(tabs.count())
            if tabs.widget(index) is not directory and tabs.widget(index) is not team
        ),
        None,
    )
    if shds is None:
        return

    settings_key = "workspace/composition_tab_order"
    prototype_key = "workspace/directory_action_panel"
    default_order = ("directory", "team", "shds")
    id_to_widget = {
        "directory": directory,
        "team": team,
        "shds": shds,
    }
    widget_to_id = {id(widget): tab_id for tab_id, widget in id_to_widget.items()}

    # Remove the superseded pilot preference. It was never personnel data and
    # must not influence the new direct-manipulation workspace behaviour.
    window.settings.remove(prototype_key)

    def parse_order(raw: Any) -> list[str] | None:
        if raw is None:
            return None
        try:
            data = raw if isinstance(raw, list) else json.loads(str(raw))
        except (TypeError, ValueError):
            return None
        if not isinstance(data, list):
            return None
        order = [str(value) for value in data]
        if len(order) != len(default_order) or len(set(order)) != len(default_order):
            return None
        if set(order) != set(default_order):
            return None
        return order

    def current_order() -> list[str]:
        order: list[str] = []
        for index in range(tabs.count()):
            tab_id = widget_to_id.get(id(tabs.widget(index)))
            if tab_id is not None:
                order.append(tab_id)
        return order

    def apply_order(order: list[str] | tuple[str, ...]) -> None:
        current_widget = tabs.currentWidget()
        tab_bar = tabs.tabBar()
        previous_block = tab_bar.blockSignals(True)
        try:
            # QTabWidget keeps its page mapping in sync through tabBar signals.
            # moveTab() with blocked signals moves only the labels and leaves
            # widget(i) pointing at the old pages, so reorder with
            # removeTab()/insertTab(), which updates the stack directly.
            for target_index, tab_id in enumerate(order):
                widget = id_to_widget[tab_id]
                current_index = tabs.indexOf(widget)
                if current_index < 0 or current_index == target_index:
                    continue
                label = tabs.tabText(current_index)
                tabs.removeTab(current_index)
                tabs.insertTab(target_index, widget, label)
            if current_widget is not None:
                tabs.setCurrentWidget(current_widget)
        finally:
            tab_bar.blockSignals(previous_block)

    saved_order = parse_order(window.settings.value(settings_key))
    if saved_order is not None:
        apply_order(saved_order)
    elif window.settings.contains(settings_key):
        # Corrupt/stale local UI state must never prevent startup.
        window.settings.remove(settings_key)
        apply_order(default_order)

    tabs.setMovable(True)

    def save_order(*_args) -> None:
        order = current_order()
        if len(order) == len(default_order):
            window.settings.setValue(settings_key, json.dumps(order, ensure_ascii=False))

    tabs.tabBar().tabMoved.connect(save_order)

    def reset_tab_order() -> None:
        apply_order(default_order)
        window.settings.remove(settings_key)

    reset_action = QAction("Сбросить порядок вкладок Состава", window)
    reset_action.triggered.connect(reset_tab_order)
    _view_menu(window).addAction(reset_action)

    # Navigation entry points themselves resolve tabs by widget identity
    # (composition_ui / manual_team_ui / interface_polish), so no extra
    # index-based handlers are layered here.
    window.composition_tab_default_order = tuple(default_order)
    window.composition_tab_current_order = current_order
    window.composition_tab_apply_order = apply_order
    window.composition_tab_parse_order = parse_order
    window.reset_composition_tab_order = reset_tab_order
    window.reset_composition_tab_order_action = reset_action


def install_custom_workspace_ui(window: Any) -> None:
    """Install the final v1.1 workspace preferences."""
    if getattr(window, "_custom_workspace_ui_installed", False):
        return

    _install_shds_columns(window)
    _install_today_tables(window)
    _install_composition_tab_order(window)
    window._custom_workspace_ui_installed = True
