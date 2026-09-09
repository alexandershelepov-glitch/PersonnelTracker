"""Modern presentation layer for the Composition directory.

This module is intentionally presentation-only.  It reuses the existing
Composition widgets, signals and services and only rearranges/stylises them so
one screen can act as the visual reference for the final application design.
"""
from __future__ import annotations

from typing import Any


def install_modern_directory_ui(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    if getattr(window, "_modern_directory_ui_installed", False):
        return

    directory = getattr(window, "composition_directory", None)
    tabs = getattr(window, "composition_tabs", None)
    table = getattr(window, "composition_directory_table", None)
    search = getattr(window, "composition_search", None)
    department = getattr(window, "composition_department", None)
    section = getattr(window, "composition_section", None)
    group = getattr(window, "composition_group", None)
    position = getattr(window, "composition_position", None)
    active_only = getattr(window, "composition_active_only", None)
    copy_mode = getattr(window, "composition_copy_mode", None)
    filter_status = getattr(window, "composition_filter_status", None)
    reset_filters = getattr(window, "composition_reset_filters", None)
    empty_state = getattr(window, "composition_empty_state", None)

    required = (
        directory,
        tabs,
        table,
        search,
        department,
        section,
        group,
        position,
        active_only,
        copy_mode,
        filter_status,
        reset_filters,
        empty_state,
    )
    if any(widget is None for widget in required):
        return

    root = directory.layout()
    if root is None:
        return

    labels = directory.findChildren(QLabel)
    intro = next(
        (label for label in labels if label.text().startswith("Быстрый справочник работников")),
        None,
    )
    if intro is not None:
        intro.setText("Поиск, фильтры и быстрый доступ к карточкам работников.")
        intro.setObjectName("directoryIntro")
        intro.setWordWrap(False)

    # Old captions belonged to the compact v0.8 layout.  Their controls are
    # re-used below, while the captions themselves are replaced with a cleaner
    # four-column filter toolbar.
    for label in labels:
        if label.text() in {"Поиск:", "Подразделение:", "Отделение:", "Группа:", "Должность:"}:
            label.hide()

    search.setObjectName("directorySearch")
    search.setPlaceholderText("Поиск по ФИО, табельному номеру, телефону или должности")
    search.setMinimumHeight(38)

    toolbar = QFrame(directory)
    toolbar.setObjectName("directoryToolbar")
    toolbar_layout = QVBoxLayout(toolbar)
    toolbar_layout.setContentsMargins(14, 12, 14, 12)
    toolbar_layout.setSpacing(10)

    search_row = QHBoxLayout()
    search_row.setSpacing(10)
    search_row.addWidget(search, 1)
    search_row.addWidget(active_only)
    toolbar_layout.addLayout(search_row)

    filters = QGridLayout()
    filters.setHorizontalSpacing(10)
    filters.setVerticalSpacing(4)
    for column, (caption, combo) in enumerate(
        (
            ("Подразделение", department),
            ("Отделение", section),
            ("Группа", group),
            ("Должность", position),
        )
    ):
        caption_label = QLabel(caption, toolbar)
        caption_label.setObjectName("directoryFieldLabel")
        filters.addWidget(caption_label, 0, column)
        filters.addWidget(combo, 1, column)
        filters.setColumnStretch(column, 1)
    toolbar_layout.addLayout(filters)

    status_row = QHBoxLayout()
    filter_status.setObjectName("directoryFilterStatus")
    reset_filters.setObjectName("directoryReset")
    reset_filters.setText("Сбросить")
    status_row.addWidget(filter_status)
    status_row.addStretch()
    status_row.addWidget(reset_filters)
    toolbar_layout.addLayout(status_row)

    insert_index = 1 if intro is not None else 0
    root.insertWidget(insert_index, toolbar)

    selected_label = next(
        (label for label in directory.findChildren(QLabel) if label.text().startswith("Выбрано")),
        None,
    )
    copy_button = next(
        (button for button in directory.findChildren(QPushButton) if button.text() == "Копировать"),
        None,
    )
    open_button = next(
        (button for button in directory.findChildren(QPushButton) if button.text() == "Открыть карточку"),
        None,
    )

    actions_frame = None
    if selected_label is not None and copy_button is not None and open_button is not None:
        actions_frame = QFrame(directory)
        actions_frame.setObjectName("directoryActions")
        actions = QHBoxLayout(actions_frame)
        actions.setContentsMargins(0, 2, 0, 2)
        actions.setSpacing(8)
        selected_label.setObjectName("directorySelection")
        copy_mode.setObjectName("directoryCopyMode")
        open_button.setObjectName("directoryOpenButton")
        actions.addWidget(selected_label)
        actions.addStretch()
        actions.addWidget(copy_mode)
        actions.addWidget(copy_button)
        actions.addWidget(open_button)
        root.insertWidget(max(0, root.indexOf(empty_state)), actions_frame)

    empty_state.setText("Сотрудники не найдены\nДобавьте работников или измените фильтры")
    empty_state.setObjectName("directoryEmptyState")
    empty_state.setWordWrap(True)
    empty_state.setAlignment(Qt.AlignCenter)

    table.setShowGrid(False)
    table.verticalHeader().setDefaultSectionSize(36)
    table.horizontalHeader().setMinimumHeight(40)

    root.setContentsMargins(12, 8, 12, 12)
    root.setSpacing(10)
    tabs.tabBar().setDrawBase(False)
    tabs.tabBar().setExpanding(False)

    def apply_styles() -> None:
        palette = window.theme_manager.palette()
        panel = palette["panel_bg"]
        window_bg = palette["window_bg"]
        border = palette["border"]
        hover = palette["hover"]
        accent = palette["accent"]
        accent_hover = palette["accent_hover"]
        text = palette["text"]
        secondary = palette["text_secondary"]
        muted = palette["muted"]
        alternate = palette["alternate_row"]

        tabs.setStyleSheet(
            f"""
            QTabWidget#compositionTabs::pane {{
                border: none;
                background: transparent;
                top: -1px;
            }}
            QTabWidget#compositionTabs QTabBar::tab {{
                background: transparent;
                color: {secondary};
                border: none;
                border-radius: 8px;
                padding: 7px 13px;
                margin: 0 3px 5px 0;
                min-height: 24px;
            }}
            QTabWidget#compositionTabs QTabBar::tab:selected {{
                background: {hover};
                color: {accent};
                font-weight: 600;
            }}
            QTabWidget#compositionTabs QTabBar::tab:hover:!selected {{
                background: {alternate};
                color: {text};
            }}
            """
        )

        directory.setStyleSheet(
            f"""
            QLabel#directoryIntro {{
                color: {secondary};
                font-size: 12px;
                padding: 1px 0 3px 0;
            }}
            QFrame#directoryToolbar {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QLabel#directoryFieldLabel {{
                color: {secondary};
                font-size: 11px;
                font-weight: 600;
                padding-left: 2px;
            }}
            QLabel#directoryFilterStatus,
            QLabel#directorySelection {{
                color: {secondary};
                font-size: 12px;
            }}
            QLabel#directoryEmptyState {{
                color: {secondary};
                font-size: 14px;
                padding: 24px;
            }}
            QLineEdit#directorySearch {{
                background: {window_bg};
                border: 1px solid {border};
                border-radius: 9px;
                padding: 7px 10px;
            }}
            QLineEdit#directorySearch:focus {{
                border: 1px solid {accent};
                background: {panel};
            }}
            QPushButton#directoryReset {{
                background: transparent;
                border: none;
                color: {accent};
                padding: 5px 7px;
            }}
            QPushButton#directoryReset:hover {{
                background: {hover};
                color: {accent_hover};
            }}
            QPushButton#directoryReset:disabled {{
                background: transparent;
                color: {muted};
            }}
            QFrame#directoryActions {{
                background: transparent;
                border: none;
            }}
            QTableWidget#compositionDirectory {{
                background: {panel};
                alternate-background-color: {window_bg};
                border: 1px solid {border};
                border-radius: 10px;
                gridline-color: transparent;
            }}
            QTableWidget#compositionDirectory QHeaderView::section {{
                background: {alternate};
                color: {secondary};
                border: none;
                border-bottom: 1px solid {border};
                padding: 8px 10px;
                font-weight: 600;
            }}
            """
        )

    original_sync = getattr(window, "_sync_theme_controls", None)
    if callable(original_sync):
        def sync_theme() -> None:
            original_sync()
            apply_styles()

        window._sync_theme_controls = sync_theme

    apply_styles()
    window.modern_directory_toolbar = toolbar
    window.modern_directory_actions = actions_frame
    window._modern_directory_ui_installed = True
