"""Focused presentation adapter for the Planning workspace.

The planner's data, callbacks and event semantics remain in ``planning_ui``.
This layer only compacts the existing controls and empty states so the screen
matches the modern Directory/Today visual language.
"""
from __future__ import annotations

from typing import Any


def install_modern_planning_ui(window: Any) -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QComboBox,
        QFrame,
        QGraphicsDropShadowEffect,
        QGridLayout,
        QLabel,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
    )

    if getattr(window, "_modern_planning_ui_installed", False):
        return

    pages = getattr(window, "pages", None)
    page = pages.widget(2) if pages is not None else None
    root = page.layout() if page is not None else None
    tabs = getattr(window, "planning_tabs", None)
    month_label = getattr(window, "planning_month_label", None)
    department = getattr(window, "planning_department", None)
    section = getattr(window, "planning_section", None)
    event_type = getattr(window, "planning_event_type", None)
    filter_status = getattr(window, "planning_filter_status", None)
    reset_filters = getattr(window, "planning_reset_filters", None)
    graph_empty = getattr(window, "planning_graph_empty", None)
    list_empty = getattr(window, "planning_list_empty", None)

    required = (
        page,
        root,
        tabs,
        month_label,
        department,
        section,
        event_type,
        filter_status,
        reset_filters,
        graph_empty,
        list_empty,
    )
    if any(item is None for item in required):
        return

    toolbar_layout = None
    filter_layout = None
    toolbar_index = None
    filter_index = None
    for index in range(root.count()):
        item = root.itemAt(index)
        layout = item.layout()
        if layout is None:
            continue
        widgets = [
            layout.itemAt(child).widget()
            for child in range(layout.count())
            if layout.itemAt(child).widget() is not None
        ]
        if month_label in widgets:
            toolbar_layout = layout
            toolbar_index = index
        if department in widgets:
            filter_layout = layout
            filter_index = index

    if toolbar_layout is None or filter_layout is None:
        return

    # Remove only the two presentation rows from the page. Their widgets,
    # signals and callbacks stay alive and are reused below.
    insertion_index = min(toolbar_index, filter_index)
    for index in sorted((toolbar_index, filter_index), reverse=True):
        root.takeAt(index)

    controls = QFrame(page)
    controls.setObjectName("planningControlPanel")
    controls_root = QVBoxLayout(controls)
    controls_root.setContentsMargins(14, 12, 14, 12)
    controls_root.setSpacing(10)

    toolbar_layout.setSpacing(8)
    controls_root.addLayout(toolbar_layout)

    # Prevent the vector plus icon and the legacy text '+' from being shown
    # together. The action itself and its callback are unchanged.
    add_event = next(
        (button for button in page.findChildren(QPushButton) if "Добавить событие" in button.text()),
        None,
    )
    if add_event is not None:
        add_event.setText("Добавить событие")
        add_event.setMinimumHeight(36)

    current_month = next(
        (button for button in page.findChildren(QPushButton) if button.text() == "Текущий месяц"),
        None,
    )
    if current_month is not None:
        current_month.setMinimumHeight(34)

    for button in page.findChildren(QPushButton):
        if button.text() in {"‹", "›"}:
            button.setFixedSize(34, 34)

    # Replace the sparse legacy filter grid with three compact equal columns.
    for child_index in reversed(range(filter_layout.count())):
        item = filter_layout.itemAt(child_index)
        widget = item.widget()
        if isinstance(widget, QLabel) and widget not in {filter_status}:
            widget.hide()

    filters = QGridLayout()
    filters.setHorizontalSpacing(10)
    filters.setVerticalSpacing(5)
    for column, (caption, combo) in enumerate(
        (
            ("Подразделение", department),
            ("Отделение", section),
            ("Событие", event_type),
        )
    ):
        filter_layout.removeWidget(combo)
        caption_label = QLabel(caption, controls)
        caption_label.setObjectName("planningFieldLabel")
        filters.addWidget(caption_label, 0, column)
        filters.addWidget(combo, 1, column)
        filters.setColumnStretch(column, 1)
        if isinstance(combo, QComboBox):
            combo.setMinimumHeight(36)

    filter_layout.removeWidget(filter_status)
    filter_layout.removeWidget(reset_filters)
    filter_status.setObjectName("planningFilterStatus")
    reset_filters.setObjectName("planningReset")
    reset_filters.setText("Сбросить")
    filters.addWidget(filter_status, 2, 0, 1, 2)
    filters.addWidget(reset_filters, 2, 2)
    controls_root.addLayout(filters)
    filter_layout.deleteLater()

    root.insertWidget(insertion_index, controls)
    root.setSpacing(10)

    # Tabs should read as the start of the working area, not a centred title.
    tabs.tabBar().setExpanding(False)

    graph = tabs.widget(0)
    graph_root = graph.layout() if graph is not None else None
    graph_hint = None
    if graph is not None:
        graph_hint = next(
            (
                label
                for label in graph.findChildren(QLabel)
                if label.text().startswith("Нажмите ФИО")
                or label.text().startswith("Сотрудники расположены по строкам")
            ),
            None,
        )
    if graph_root is not None:
        graph_root.setContentsMargins(0, 8, 0, 0)
        graph_root.setSpacing(10)

    if graph_hint is not None:
        graph_hint.setText(
            "Нажмите ФИО — добавить событие работнику. Дважды нажмите пустой день — "
            "добавить событие на конкретную дату. Нажмите существующее событие — открыть его."
        )
        graph_hint.setObjectName("planningHint")
        graph_hint.setMaximumHeight(48)
        graph_hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    for label in (graph_empty, list_empty):
        label.setObjectName("planningEmptyState")
        label.setMinimumHeight(88)
        label.setMaximumHeight(112)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    shadow = QGraphicsDropShadowEffect(controls)
    shadow.setBlurRadius(24)
    shadow.setOffset(0, 4)
    shadow.setColor(QColor(15, 23, 42, 25))
    controls.setGraphicsEffect(shadow)

    def apply_styles() -> None:
        palette = window.theme_manager.palette()
        panel = palette["panel_bg"]
        border = palette["border"]
        text = palette["text"]
        secondary = palette["text_secondary"]
        alternate = palette["alternate_row"]
        accent = palette["accent"]
        hover = palette["hover"]

        controls.setStyleSheet(
            f"""
            QFrame#planningControlPanel {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QFrame#planningControlPanel QLabel {{
                border: none;
                background: transparent;
            }}
            QLabel#planningFieldLabel {{
                color: {secondary};
                font-size: 11px;
                font-weight: 600;
                padding-left: 2px;
            }}
            QLabel#planningFilterStatus {{
                color: {secondary};
                font-size: 12px;
            }}
            QPushButton#planningReset {{
                background: transparent;
                color: {accent};
                border: none;
                padding: 6px 8px;
            }}
            QPushButton#planningReset:hover {{
                background: {hover};
            }}
            """
        )

        if graph is not None:
            graph.setStyleSheet(
                f"""
                QLabel#planningHint {{
                    color: {secondary};
                    background: transparent;
                    border: none;
                    padding: 2px 0 6px 0;
                    font-size: 12px;
                }}
                QLabel#planningEmptyState {{
                    color: {secondary};
                    background: {alternate};
                    border: 1px solid {border};
                    border-radius: 10px;
                    padding: 18px;
                    font-size: 13px;
                }}
                """
            )
        list_empty.setStyleSheet(
            f"color: {secondary}; background: {alternate}; border: 1px solid {border}; "
            "border-radius: 10px; padding: 18px; font-size: 13px;"
        )

    original_sync = getattr(window, "_sync_theme_controls", None)
    if callable(original_sync):
        def sync_theme() -> None:
            original_sync()
            apply_styles()

        window._sync_theme_controls = sync_theme

    apply_styles()
    window.modern_planning_controls = controls
    window.modern_planning_controls_shadow = shadow
    window.modern_planning_hint = graph_hint
    window._modern_planning_ui_installed = True
