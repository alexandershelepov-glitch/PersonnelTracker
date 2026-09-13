"""v1.1 user-customizable workspace preferences.

Presentation only. Preferences are stored in QSettings and never modify
personnel data, assignment history or database schema.
"""
from __future__ import annotations

from typing import Any


def _view_menu(window: Any):
    from PySide6.QtWidgets import QMenu

    for menu_action in window.menuBar().actions():
        menu = menu_action.menu()
        if isinstance(menu, QMenu) and menu.title() == "Вид":
            return menu
    return window.menuBar().addMenu("Вид")


def _install_shds_columns(window: Any) -> None:
    """Keep the existing v1.1 movable/persistent SHDS column behaviour."""
    from PySide6.QtGui import QAction

    table = getattr(window, "staff_table", None)
    if table is None:
        return

    shds_header = table.horizontalHeader()
    shds_header.setSectionsMovable(True)

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
            for target_index, tab_id in enumerate(order):
                widget = id_to_widget[tab_id]
                current_index = tabs.indexOf(widget)
                if current_index >= 0 and current_index != target_index:
                    tab_bar.moveTab(current_index, target_index)
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

    # composition_ui.py predates movable tabs and its quick navigation uses
    # factory indexes 0/1. Add final identity-based selectors so those entry
    # points keep opening the intended page after the user reorders tabs.
    composition_button = window.nav_group.button(0)
    if composition_button is not None:
        composition_button.clicked.connect(
            lambda _checked=False: tabs.setCurrentWidget(directory)
        )

    if hasattr(window, "today_page") and hasattr(window.today_page, "team"):
        window.today_page.team.clicked.connect(lambda: tabs.setCurrentWidget(team))

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
    _install_composition_tab_order(window)
    window._custom_workspace_ui_installed = True
