"""Modern application chrome for the visual design prototype.

Presentation only. Adds a restrained sidebar treatment and small vector icons
without external icon/font dependencies or changes to navigation/business logic.
"""
from __future__ import annotations

from typing import Any


def install_modern_chrome_ui(window: Any) -> None:
    from PySide6.QtCore import QRectF, QSize, Qt
    from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QPushButton

    if getattr(window, "_modern_chrome_ui_installed", False):
        return

    sidebar = window.findChild(QFrame, "sidebar")
    search = getattr(window, "composition_search", None)
    if sidebar is None:
        return

    def line_icon(kind: str, color: str, size: int = 20) -> QIcon:
        """Draw a tiny dependency-free outline icon suitable for Retina Qt UI."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(color))
        pen.setWidthF(1.65)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if kind in {"today", "planning"}:
            painter.drawRoundedRect(QRectF(3.0, 4.5, 14.0, 12.5), 2.2, 2.2)
            painter.drawLine(3.2, 8.0, 16.8, 8.0)
            painter.drawLine(6.2, 2.8, 6.2, 6.1)
            painter.drawLine(13.8, 2.8, 13.8, 6.1)
            if kind == "today":
                painter.setBrush(QColor(color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRectF(8.15, 10.2, 3.7, 3.7))
            else:
                painter.drawLine(6.0, 11.0, 10.0, 11.0)
                painter.drawLine(6.0, 14.0, 13.5, 14.0)
        elif kind == "people":
            painter.drawEllipse(QRectF(4.0, 3.2, 5.5, 5.5))
            painter.drawEllipse(QRectF(11.6, 4.6, 4.2, 4.2))
            painter.drawArc(QRectF(2.2, 8.5, 9.2, 8.3), 20 * 16, 140 * 16)
            painter.drawArc(QRectF(9.2, 9.0, 8.4, 7.2), 22 * 16, 128 * 16)
        elif kind == "settings":
            for y, knob in ((5.0, 7.0), (10.0, 13.0), (15.0, 9.0)):
                painter.drawLine(3.0, y, 17.0, y)
                painter.setBrush(QColor(color))
                painter.drawEllipse(QRectF(knob - 1.5, y - 1.5, 3.0, 3.0))
                painter.setBrush(Qt.NoBrush)
        elif kind == "search":
            painter.drawEllipse(QRectF(3.2, 3.2, 9.8, 9.8))
            painter.drawLine(12.0, 12.0, 17.0, 17.0)
        elif kind == "copy":
            painter.drawRoundedRect(QRectF(6.0, 5.0, 10.0, 11.0), 1.8, 1.8)
            painter.drawRoundedRect(QRectF(3.2, 2.3, 10.0, 11.0), 1.8, 1.8)
        elif kind == "open":
            painter.drawRoundedRect(QRectF(3.2, 4.0, 11.3, 12.4), 1.8, 1.8)
            painter.drawLine(10.5, 3.5, 16.7, 3.5)
            painter.drawLine(16.5, 3.7, 16.5, 9.7)
            painter.drawLine(16.2, 3.8, 9.4, 10.6)
        elif kind == "reset":
            painter.drawArc(QRectF(3.0, 3.0, 14.0, 14.0), 40 * 16, 285 * 16)
            painter.drawLine(3.9, 4.2, 3.3, 8.0)
            painter.drawLine(3.9, 4.2, 7.6, 4.8)
        elif kind == "plus":
            painter.drawLine(10.0, 4.0, 10.0, 16.0)
            painter.drawLine(4.0, 10.0, 16.0, 10.0)

        painter.end()
        return QIcon(pixmap)

    icon_kinds = {
        "Сегодня": "today",
        "Состав": "people",
        "Планирование": "planning",
        "Настройки": "settings",
    }

    sidebar.setMinimumWidth(196)
    sidebar.setMaximumWidth(224)

    visible_nav: list[QPushButton] = []
    for button in getattr(window, "nav_buttons", []):
        if button.text() in icon_kinds:
            button.setIconSize(QSize(18, 18))
            button.setMinimumHeight(40)
            visible_nav.append(button)

    # A leading search icon is attached once; recolouring it on theme changes
    # is cheaper and more reliable than shipping raster assets in the bundle.
    search_action = None
    if isinstance(search, QLineEdit):
        search_action = QAction(search)
        search.addAction(search_action, QLineEdit.LeadingPosition)

    def find_button(text: str):
        directory = getattr(window, "composition_directory", None)
        if directory is None:
            return None
        return next((b for b in directory.findChildren(QPushButton) if b.text() == text), None)

    copy_button = find_button("Копировать")
    open_button = find_button("Открыть карточку")
    reset_button = getattr(window, "composition_reset_filters", None)

    # Give page titles more hierarchy without changing individual page layouts.
    for label in window.findChildren(QLabel):
        if label.objectName() == "pageTitle":
            label.setStyleSheet("font-size: 21px; font-weight: 700; padding: 1px 0 2px 0;")

    def apply_chrome() -> None:
        palette = window.theme_manager.palette()
        panel = palette["panel_bg"]
        window_bg = palette["window_bg"]
        hover = palette["hover"]
        alternate = palette["alternate_row"]
        accent = palette["accent"]
        text = palette["text"]
        secondary = palette["text_secondary"]
        border = palette["border"]
        accent_text = palette["accent_text"]

        sidebar.setStyleSheet(
            f"""
            QFrame#sidebar {{
                background: {window_bg};
                border: none;
                border-right: 1px solid {border};
            }}
            QFrame#sidebar QLabel#appTitle {{
                color: {text};
                font-size: 16px;
                font-weight: 700;
                padding: 17px 12px 2px 12px;
            }}
            QFrame#sidebar QLabel#appSubtitle {{
                color: {secondary};
                font-size: 11px;
                padding: 0 12px 12px 12px;
            }}
            QFrame#sidebar QPushButton[navButton="true"] {{
                background: transparent;
                color: {secondary};
                border: none;
                border-left: 3px solid transparent;
                border-radius: 9px;
                padding: 8px 11px;
                text-align: left;
                font-weight: 500;
            }}
            QFrame#sidebar QPushButton[navButton="true"]:hover {{
                background: {alternate};
                color: {text};
            }}
            QFrame#sidebar QPushButton[navButton="true"]:checked {{
                background: {hover};
                color: {accent};
                border-left: 3px solid {accent};
                font-weight: 600;
            }}
            """
        )

        for button in visible_nav:
            kind = icon_kinds[button.text()]
            button.setIcon(line_icon(kind, accent if button.isChecked() else secondary, 20))

        if search_action is not None:
            search_action.setIcon(line_icon("search", secondary, 18))
        if copy_button is not None:
            copy_button.setIcon(line_icon("copy", accent_text, 18))
            copy_button.setIconSize(QSize(16, 16))
        if open_button is not None:
            open_button.setIcon(line_icon("open", secondary, 18))
            open_button.setIconSize(QSize(16, 16))
        if isinstance(reset_button, QPushButton):
            reset_button.setIcon(line_icon("reset", accent, 17))
            reset_button.setIconSize(QSize(15, 15))

        today_page = getattr(window, "today_page", None)
        if today_page is not None:
            add_event = getattr(today_page, "add_event", None)
            team = getattr(today_page, "team", None)
            if isinstance(add_event, QPushButton):
                add_event.setIcon(line_icon("plus", accent_text, 18))
                add_event.setIconSize(QSize(16, 16))
            if isinstance(team, QPushButton):
                team.setIcon(line_icon("people", secondary, 18))
                team.setIconSize(QSize(16, 16))

    for button in visible_nav:
        button.toggled.connect(lambda _checked=False: apply_chrome())

    original_sync = getattr(window, "_sync_theme_controls", None)
    if callable(original_sync):
        def sync_theme() -> None:
            original_sync()
            apply_chrome()

        window._sync_theme_controls = sync_theme

    apply_chrome()
    window.modern_sidebar = sidebar
    window.modern_sidebar_buttons = visible_nav
    window.modern_search_action = search_action
    window._modern_chrome_ui_installed = True
