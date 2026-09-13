"""Small acceptance-stage UI fixes without changing personnel workflows."""
from __future__ import annotations

from typing import Any


def install_acceptance_ui_polish(window: Any) -> None:
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtWidgets import (
        QApplication,
        QCalendarWidget,
        QMessageBox,
        QPushButton,
    )

    if getattr(window, "_acceptance_ui_polish_installed", False):
        return

    # SHDS column order/width/visibility is owned by the v1.1 workspace layer
    # (QSettings "workspace/shds_header_state"); this layer no longer competes
    # for it by re-applying legacy SQLite widths.

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
        @staticmethod
        def _size_message_box(box, buttons) -> None:
            try:
                box.setMinimumWidth(max(box.minimumWidth(), 760))
                for button in buttons:
                    button.setMinimumWidth(max(button.minimumWidth(), 230))
            except RuntimeError:
                # The dialog was already destroyed before the deferred pass.
                pass

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show:
                if isinstance(obj, QMessageBox):
                    buttons = obj.findChildren(QPushButton)
                    long_buttons = [button for button in buttons if len(button.text().strip()) >= 22]
                    if long_buttons:
                        # Event filters run before the widget's own showEvent,
                        # where QMessageBox recomputes its size and would drop
                        # the constraint. Apply now and once more after layout.
                        self._size_message_box(obj, long_buttons)
                        QTimer.singleShot(0, lambda box=obj, items=long_buttons: self._size_message_box(box, items))
                elif isinstance(obj, QCalendarWidget):
                    obj.setStyleSheet(calendar_style)
            return False

    app = QApplication.instance()
    filter_object = None
    if app is not None:
        # One application-wide presentation filter. Parenting it to a window
        # made it disappear with that window and left later message boxes
        # unsized (visible in test batches that open several main windows).
        filter_object = getattr(app, "_acceptance_presentation_filter", None)
        if filter_object is None:
            filter_object = AcceptancePresentationFilter(app)
            app.installEventFilter(filter_object)
            app._acceptance_presentation_filter = filter_object

    window.acceptance_presentation_filter = filter_object
    # Preserve the previous attribute for compatibility with the focused tests
    # and any local diagnostic code created during acceptance.
    window.acceptance_messagebox_filter = filter_object
    window._acceptance_ui_polish_installed = True
