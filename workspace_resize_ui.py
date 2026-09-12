"""Resizable workspace polish for PersonnelTracker.

Presentation only:
- Directory keeps filters compact and gives remaining height to its data/empty area.
- Directory columns are movable/resizable and persist their layout locally.
- Planning employee columns become user-resizable and persist their widths.
- Summary work areas use nested splitters so the user controls vertical and
  horizontal proportions without changing personnel/business data.
"""
from __future__ import annotations

from typing import Any


def install_workspace_resize_ui(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QHeaderView, QMenu, QSplitter, QVBoxLayout, QWidget

    if getattr(window, "_workspace_resize_ui_installed", False):
        return

    # ------------------------------------------------------------------
    # Directory: the table used to be the only stretchable item. When an
    # empty database hid that table, Qt distributed spare height among labels
    # and controls, producing large gaps and a vertically stretched intro.
    # Give the same workspace stretch to the empty-state label so whichever
    # content widget is visible consumes the remaining height below filters.
    # ------------------------------------------------------------------
    directory = getattr(window, "composition_directory", None)
    directory_table = getattr(window, "composition_directory_table", None)
    directory_empty = getattr(window, "composition_empty_state", None)
    if directory is not None and directory.layout() is not None:
        directory_layout = directory.layout()
        if directory_table is not None:
            directory_layout.setStretchFactor(directory_table, 1)
        if directory_empty is not None:
            directory_layout.setStretchFactor(directory_empty, 1)

    # v1.1 starts with one high-value table rather than making every grid
    # configurable at once. QHeaderView already serializes visual order, widths
    # and hidden sections, so keep the preference local in QSettings and leave
    # personnel/database records untouched.
    if directory_table is not None:
        header = directory_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setMinimumSectionSize(72)

        defaults = (220, 180, 110, 145, 240, 105)
        for column in range(directory_table.columnCount()):
            if directory_table.isColumnHidden(column):
                continue
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            if column < len(defaults):
                directory_table.setColumnWidth(column, defaults[column])

        default_state = header.saveState()
        settings_key = "workspace/directory_header_state"
        saved_header = window.settings.value(settings_key)
        if saved_header:
            header.blockSignals(True)
            restored = header.restoreState(saved_header)
            if not restored:
                header.restoreState(default_state)
            header.blockSignals(False)

        def save_directory_header(*_args) -> None:
            window.settings.setValue(settings_key, header.saveState())

        def reset_directory_header() -> None:
            header.blockSignals(True)
            try:
                header.restoreState(default_state)
                # restoreState restores sizes/hidden flags and, in practice, the
                # visual order too.  Move every logical section back to its
                # factory slot explicitly so the reset is deterministic even on
                # Qt builds where restoreState alone does not reorder after
                # moveSection.
                for logical in range(header.count()):
                    visual = header.visualIndex(logical)
                    if visual != logical:
                        header.moveSection(visual, logical)
            finally:
                header.blockSignals(False)
            # Never let the sectionMoved/sectionResized handlers above write the
            # intermediate reset state back into QSettings.
            window.settings.remove(settings_key)

        header.sectionMoved.connect(save_directory_header)
        header.sectionResized.connect(save_directory_header)
        header.sectionDoubleClicked.connect(directory_table.resizeColumnToContents)

        view_menu = None
        for action in window.menuBar().actions():
            menu = action.menu()
            if isinstance(menu, QMenu) and menu.title() == "Вид":
                view_menu = menu
                break
        if view_menu is None:
            view_menu = window.menuBar().addMenu("Вид")

        reset_directory_action = QAction("Сбросить колонки справочника", window)
        reset_directory_action.triggered.connect(reset_directory_header)
        view_menu.addAction(reset_directory_action)

        window.directory_header = header
        window.directory_default_header_state = default_state
        window.reset_directory_columns = reset_directory_header
        window.reset_directory_columns_action = reset_directory_action

    # ------------------------------------------------------------------
    # Planning: keep the outer splitter, but let the user control the three
    # identity columns inside the fixed-left table as well.
    # ------------------------------------------------------------------
    people = getattr(window, "planning_people_table", None)
    if people is not None:
        people_header = people.horizontalHeader()
        people_header.setStretchLastSection(False)
        people_header.setMinimumSectionSize(72)
        for column in range(min(3, people.columnCount())):
            people_header.setSectionResizeMode(column, QHeaderView.Interactive)

        saved_header = window.settings.value("planning/people_header_state")
        if saved_header:
            people_header.restoreState(saved_header)
        else:
            defaults = (200, 165, 125)
            for column, width in enumerate(defaults):
                if column < people.columnCount():
                    people.setColumnWidth(column, width)

        def save_people_header(*_args) -> None:
            window.settings.setValue("planning/people_header_state", people_header.saveState())

        people_header.sectionResized.connect(save_people_header)
        # Familiar desktop gesture: double-click a divider to fit that column.
        people_header.sectionDoubleClicked.connect(people.resizeColumnToContents)
        window.planning_people_header = people_header

    # ------------------------------------------------------------------
    # Summary: replace the rigid top-table + fixed HBox below it with nested
    # splitters. The toolbar above remains untouched.
    # ------------------------------------------------------------------
    summary_table = getattr(window, "summary_table", None)
    summary_tree = getattr(window, "summary_tree", None)
    summary_people = getattr(window, "summary_people", None)
    if summary_table is not None and summary_tree is not None and summary_people is not None:
        summary_tab = summary_table.parentWidget()
        root = summary_tab.layout() if summary_tab is not None else None
        if root is not None:
            table_index = root.indexOf(summary_table)
            diagnostic = getattr(window, "diagnostic_label", None)

            # Locate the old bottom QHBoxLayout containing the tree and people
            # table, then detach those widgets before replacing the layout.
            bottom_layout = None
            for index in range(root.count()):
                item = root.itemAt(index)
                layout = item.layout()
                if layout is not None and layout.indexOf(summary_tree) >= 0:
                    bottom_layout = layout
                    break

            if table_index >= 0 and bottom_layout is not None:
                root.removeWidget(summary_table)
                if diagnostic is not None:
                    root.removeWidget(diagnostic)
                bottom_layout.removeWidget(summary_tree)
                bottom_layout.removeWidget(summary_people)
                for index in range(root.count()):
                    if root.itemAt(index).layout() is bottom_layout:
                        root.takeAt(index)
                        break
                bottom_layout.deleteLater()

                top_panel = QWidget(summary_tab)
                top_layout = QVBoxLayout(top_panel)
                top_layout.setContentsMargins(0, 0, 0, 0)
                top_layout.setSpacing(6)
                top_layout.addWidget(summary_table, 1)
                if diagnostic is not None:
                    top_layout.addWidget(diagnostic)

                horizontal = QSplitter(Qt.Horizontal, summary_tab)
                horizontal.addWidget(summary_tree)
                horizontal.addWidget(summary_people)
                horizontal.setChildrenCollapsible(False)
                horizontal.setStretchFactor(0, 1)
                horizontal.setStretchFactor(1, 2)
                horizontal.setSizes([340, 680])

                vertical = QSplitter(Qt.Vertical, summary_tab)
                vertical.addWidget(top_panel)
                vertical.addWidget(horizontal)
                vertical.setChildrenCollapsible(False)
                vertical.setStretchFactor(0, 1)
                vertical.setStretchFactor(1, 1)
                vertical.setSizes([220, 320])

                saved_vertical = window.settings.value("summary/vertical_splitter_state")
                saved_horizontal = window.settings.value("summary/horizontal_splitter_state")
                if saved_vertical:
                    vertical.restoreState(saved_vertical)
                if saved_horizontal:
                    horizontal.restoreState(saved_horizontal)

                vertical.splitterMoved.connect(
                    lambda _position, _index: window.settings.setValue(
                        "summary/vertical_splitter_state", vertical.saveState()
                    )
                )
                horizontal.splitterMoved.connect(
                    lambda _position, _index: window.settings.setValue(
                        "summary/horizontal_splitter_state", horizontal.saveState()
                    )
                )

                root.insertWidget(max(0, table_index), vertical, 1)
                window.summary_vertical_splitter = vertical
                window.summary_horizontal_splitter = horizontal

    window._workspace_resize_ui_installed = True
