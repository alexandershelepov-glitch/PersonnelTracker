"""Resizable workspace polish for PersonnelTracker v0.8.3.

Presentation only:
- Planning employee columns become user-resizable and persist their widths.
- Summary work areas use nested splitters so the user controls vertical and
  horizontal proportions without changing personnel/business data.
"""
from __future__ import annotations

from typing import Any


def install_workspace_resize_ui(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHeaderView, QSplitter, QVBoxLayout, QWidget

    if getattr(window, "_workspace_resize_ui_installed", False):
        return

    # ------------------------------------------------------------------
    # Planning: keep the outer splitter, but let the user control the three
    # identity columns inside the fixed-left table as well.
    # ------------------------------------------------------------------
    people = getattr(window, "planning_people_table", None)
    if people is not None:
        header = people.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(72)
        for column in range(min(3, people.columnCount())):
            header.setSectionResizeMode(column, QHeaderView.Interactive)

        saved_header = window.settings.value("planning/people_header_state")
        if saved_header:
            header.restoreState(saved_header)
        else:
            defaults = (200, 165, 125)
            for column, width in enumerate(defaults):
                if column < people.columnCount():
                    people.setColumnWidth(column, width)

        def save_people_header(*_args) -> None:
            window.settings.setValue("planning/people_header_state", header.saveState())

        header.sectionResized.connect(save_people_header)
        # Familiar desktop gesture: double-click a divider to fit that column.
        header.sectionDoubleClicked.connect(people.resizeColumnToContents)
        window.planning_people_header = header

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
