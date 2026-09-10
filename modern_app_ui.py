"""App-wide presentation layer for the modern PersonnelTracker design.

This module deliberately changes presentation only. It applies shared action
icons, restrained semantic emphasis and a small amount of elevation to the
existing workflows without moving widgets between their proven layouts.
"""
from __future__ import annotations

from typing import Any

from modern_icons import line_icon


def install_modern_app_ui(window: Any) -> None:
    from PySide6.QtCore import QEvent, QObject, QSize, Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFrame,
        QGraphicsDropShadowEffect,
        QLabel,
        QPushButton,
    )

    if getattr(window, "_modern_app_ui_installed", False):
        return

    app = QApplication.instance()
    if app is None:
        return

    def icon_kind(text: str) -> str | None:
        clean = " ".join((text or "").replace("←", "").replace("+", "").split()).casefold()
        checks = (
            (("удалить",), "delete"),
            (("сохранить",), "save"),
            (("обновить", "пересчитать"), "refresh"),
            (("копировать",), "copy"),
            (("экспорт", "выгруз"), "export"),
            (("резервн", "создать копию"), "backup"),
            (("восстанов",), "restore"),
            (("календар", "выбрать дату"), "calendar"),
            (("сброс",), "reset"),
            (("назад",), "back"),
            (("редакт", "изменить"), "edit"),
            (("открыть",), "open"),
            (("добавить", "создать", "назначить"), "plus"),
            (("отчёт",), "report"),
        )
        for needles, kind in checks:
            if any(needle in clean for needle in needles):
                return kind
        return None

    def polish_button(button: QPushButton) -> None:
        if button.property("navButton"):
            return
        text = button.text() or ""
        lowered = text.casefold()
        if "удалить" in lowered and button.property("role") != "primary":
            button.setProperty("role", "danger")
            button.style().unpolish(button)
            button.style().polish(button)

        kind = icon_kind(text)
        if kind is None:
            return
        palette = window.theme_manager.palette()
        if button.property("role") == "primary":
            colour = palette["accent_text"]
        elif button.property("role") == "danger":
            colour = palette["error"]
        else:
            colour = palette["text_secondary"]
        button.setIcon(line_icon(kind, colour, 18))
        button.setIconSize(QSize(16, 16))
        button.setProperty("modernIconKind", kind)

    class ButtonPolishFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show and isinstance(obj, QPushButton):
                polish_button(obj)
            return False

    filter_object = ButtonPolishFilter(window)
    app.installEventFilter(filter_object)

    # Planning keeps its proven structure; only typography, spacing and filter
    # controls are marked for the common visual language.
    planning_page = window.pages.widget(2) if getattr(window, "pages", None) is not None else None
    planning_root = planning_page.layout() if planning_page is not None else None
    if planning_root is not None:
        planning_root.setSpacing(12)
    month_label = getattr(window, "planning_month_label", None)
    if isinstance(month_label, QLabel):
        month_label.setObjectName("planningMonthLabel")
    planning_filters = [
        getattr(window, "planning_department", None),
        getattr(window, "planning_section", None),
        getattr(window, "planning_event_type", None),
    ]
    for combo in planning_filters:
        if isinstance(combo, QComboBox):
            combo.setProperty("modernFilter", True)
            combo.setMinimumHeight(34)

    def shadow(widget, blur: float, y: float, alpha: int):
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(0, y)
        effect.setColor(QColor(15, 23, 42, alpha))
        widget.setGraphicsEffect(effect)
        return effect

    elevation_effects = []
    today = getattr(window, "today_page", None)
    if today is not None:
        for frame in today.findChildren(QFrame):
            if frame.objectName() == "todayMetric":
                elevation_effects.append(shadow(frame, 18, 3, 22))
        attention = getattr(today, "attention_panel", None)
        if attention is not None:
            elevation_effects.append(shadow(attention, 20, 3, 20))

    def apply_app_visuals() -> None:
        palette = window.theme_manager.palette()
        border = palette["border"]
        text = palette["text"]
        secondary = palette["text_secondary"]
        alternate = palette["alternate_row"]

        if isinstance(planning_page, object) and planning_page is not None:
            planning_page.setStyleSheet(
                f"""
                QLabel#planningMonthLabel {{
                    color: {text};
                    font-size: 16px;
                    font-weight: 650;
                    padding: 0 4px;
                }}
                QComboBox[modernFilter="true"] {{
                    background: {window.theme_manager.palette()['panel_bg']};
                    border: 1px solid {border};
                    border-radius: 8px;
                    padding: 6px 9px;
                }}
                """
            )

        # Centred empty states look intentional instead of like missing tables.
        for label in window.findChildren(QLabel):
            if (
                label.objectName() == "secondaryText"
                and label.alignment() & Qt.AlignHCenter
            ):
                label.setStyleSheet(
                    f"color: {secondary}; background: {alternate}; "
                    f"border: 1px solid {border}; border-radius: 10px; padding: 18px;"
                )

        for widget in app.allWidgets():
            if isinstance(widget, QPushButton):
                polish_button(widget)

    original_sync = getattr(window, "_sync_theme_controls", None)
    if callable(original_sync):
        def sync_theme() -> None:
            original_sync()
            apply_app_visuals()

        window._sync_theme_controls = sync_theme

    apply_app_visuals()
    window.modern_app_button_filter = filter_object
    window.modern_app_elevation_effects = elevation_effects
    window.polish_modern_button = polish_button
    window._modern_app_ui_installed = True
