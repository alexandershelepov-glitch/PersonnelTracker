"""Small acceptance-stage UI fixes without changing personnel workflows."""
from __future__ import annotations

import json
from typing import Any


def install_acceptance_ui_polish(window: Any) -> None:
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import (
        QApplication,
        QCalendarWidget,
        QHeaderView,
        QMessageBox,
        QPushButton,
    )

    if getattr(window, "_acceptance_ui_polish_installed", False):
        return

    # SHDS: Position and FIO used Stretch mode in the legacy layout, so their
    # dividers could not be dragged. Restore the same Interactive behaviour as
    # the other columns while respecting previously saved user widths.
    table = getattr(window, "staff_table", None)
    headers = getattr(window, "staff_headers", [])
    if table is not None:
        header = table.horizontalHeader()
        try:
            saved_widths = json.loads(window.db.get_setting("shds_column_widths", "{}"))
        except (json.JSONDecodeError, TypeError):
            saved_widths = {}
        for name, default_width in (("Должность", 180), ("ФИО", 220)):
            if name not in headers:
                continue
            column = headers.index(name)
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            saved = saved_widths.get(name)
            width = int(saved) if saved is not None else default_width
            table.setColumnWidth(column, max(100, min(width, 420)))

    # The global theme intentionally pads QTableView cells, but QCalendarWidget
    # uses a compact internal QTableView too. Two-digit dates then have too
    # little space and Qt elides them to "...". Override only the calendar's
    # internal table so ordinary application tables keep their modern spacing.
    calendar_style = """
        QTableView {
            border: none;
            border-radius: 0px;
        }
        QTableView::item {
            padding: 0px;
        }
        QHeaderView::section {
            padding: 2px 0px;
        }
    """

    # macOS sizes QMessageBox primarily from its message text. With long custom
    # action captions this can clip labels badly. Apply presentation sizing on
    # show, independent of the business action that created the message box.
    # The same app-wide filter also fixes lazily created calendar popups.
    class AcceptancePresentationFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show:
                if isinstance(obj, QMessageBox):
                    buttons = obj.findChildren(QPushButton)
                    long_buttons = [button for button in buttons if len(button.text().strip()) >= 22]
                    if long_buttons:
                        obj.setMinimumWidth(max(obj.minimumWidth(), 760))
                        for button in long_buttons:
                            button.setMinimumWidth(max(button.minimumWidth(), 230))
                elif isinstance(obj, QCalendarWidget):
                    obj.setStyleSheet(calendar_style)
            return False

    app = QApplication.instance()
    filter_object = AcceptancePresentationFilter(window)
    if app is not None:
        app.installEventFilter(filter_object)

    window.acceptance_presentation_filter = filter_object
    # Preserve the previous attribute for compatibility with the focused tests
    # and any local diagnostic code created during acceptance.
    window.acceptance_messagebox_filter = filter_object
    window._acceptance_ui_polish_installed = True
