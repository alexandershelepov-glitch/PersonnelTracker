"""Small usability fixes for the v0.8.3 monthly planner.

Keeps the planner implementation and event model unchanged.  This adapter only
locks both halves of the split month grid to one geometry and adds an intuitive
shortcut: clicking an employee name opens the existing EventDialog with that
employee already selected.
"""
from __future__ import annotations

from typing import Any


def install_planning_usability(window: Any) -> None:
    from PySide6.QtCore import QDate, QLocale, Qt
    from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel

    if getattr(window, "_planning_usability_installed", False):
        return
    if not hasattr(window, "planning_people_table") or not hasattr(window, "planning_days_table"):
        return

    people = window.planning_people_table
    days = window.planning_days_table
    row_height = 32
    header_height = 56

    # The planner is intentionally split into two tables so employee columns
    # stay fixed while the month scrolls horizontally.  Lock both halves to the
    # same row/header geometry and pixel scrolling so long personnel lists never
    # drift out of alignment.
    for table in (people, days):
        table.setWordWrap(False)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        vertical = table.verticalHeader()
        vertical.setSectionResizeMode(QHeaderView.Fixed)
        vertical.setDefaultSectionSize(row_height)
        vertical.setMinimumSectionSize(row_height)
        vertical.setMaximumSectionSize(row_height)
        table.horizontalHeader().setFixedHeight(header_height)
        table.verticalScrollBar().setSingleStep(row_height)

    def enforce_row_geometry() -> None:
        count = min(people.rowCount(), days.rowCount())
        for row in range(count):
            people.setRowHeight(row, row_height)
            days.setRowHeight(row, row_height)

    enforce_row_geometry()

    # Make the working gesture explicit without adding another button to every
    # row.  Only the FIO cell creates a new event; other columns remain passive.
    people.setToolTip("Нажмите на ФИО, чтобы добавить событие этому работнику.")

    ru_locale = QLocale("ru_RU")

    def date_from_visible_month() -> QDate:
        today = QDate.currentDate()
        label = getattr(window, "planning_month_label", None)
        title = label.text().strip() if isinstance(label, QLabel) else ""
        if not title:
            return today
        parts = title.rsplit(" ", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            return today
        year = int(parts[1])
        name = parts[0].casefold()
        month = next(
            (
                number
                for number in range(1, 13)
                if name in {
                    ru_locale.monthName(number, QLocale.LongFormat).casefold(),
                    ru_locale.standaloneMonthName(number, QLocale.LongFormat).casefold(),
                }
            ),
            0,
        )
        if not month:
            return today
        if today.year() == year and today.month() == month:
            return today
        return QDate(year, month, 1)

    def employee_clicked(row: int, column: int) -> None:
        if column != 0:
            return
        item = people.item(row, 0)
        employee_id = item.data(Qt.UserRole) if item is not None else None
        if employee_id is None:
            return
        window.open_new_planning_event(int(employee_id), date_from_visible_month())

    people.cellClicked.connect(employee_clicked)

    # Refreshes recreate table rows, therefore re-assert geometry afterwards.
    # Existing planner refresh semantics remain the source of truth.
    original_refresh_planning = getattr(window, "refresh_planning", None)
    if callable(original_refresh_planning):
        def refresh_planning(*args, **kwargs):
            result = original_refresh_planning(*args, **kwargs)
            enforce_row_geometry()
            return result
        window.refresh_planning = refresh_planning

    original_refresh_all = window.refresh_all

    def refresh_all() -> None:
        original_refresh_all()
        enforce_row_geometry()

    window.refresh_all = refresh_all
    window._planning_usability_installed = True
