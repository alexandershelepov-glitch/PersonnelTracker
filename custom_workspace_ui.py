"""v1.1 user-customizable workspace preferences.

Presentation only. Preferences are stored in QSettings and never modify
personnel data, assignment history or database schema.
"""
from __future__ import annotations

from typing import Any


def install_custom_workspace_ui(window: Any) -> None:
    """Enable persistent SHDS column order without replacing legacy widths."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu

    if getattr(window, "_custom_workspace_ui_installed", False):
        return

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
            # moveSection() works with visual indexes. Resolve the current visual
            # index on every iteration so reset remains deterministic after any
            # user order.
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
            # Columns already hidden by the application are implementation
            # details and must not reappear because of stale saved state.
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

    view_menu = None
    for menu_action in window.menuBar().actions():
        menu = menu_action.menu()
        if isinstance(menu, QMenu) and menu.title() == "Вид":
            view_menu = menu
            break
    if view_menu is None:
        view_menu = window.menuBar().addMenu("Вид")

    reset_action = QAction("Сбросить колонки ШДС", window)
    reset_action.triggered.connect(reset_shds_header)
    view_menu.addAction(reset_action)

    window.shds_custom_header = shds_header
    window.shds_default_widths = default_widths
    window.shds_default_hidden = default_hidden
    window.reset_shds_columns = reset_shds_header
    window.reset_shds_columns_action = reset_action
    window._custom_workspace_ui_installed = True
