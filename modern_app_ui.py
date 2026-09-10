"""App-wide presentation layer for the modern PersonnelTracker design.

This module deliberately changes presentation only. It applies shared action
icons, restrained semantic emphasis and a small amount of elevation to the
existing workflows without moving business rules out of their current owners.
"""
from __future__ import annotations

from typing import Any

from modern_icons import line_icon


def install_modern_app_ui(window: Any) -> None:
    from PySide6.QtCore import QEvent, QObject, QSize
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGraphicsDropShadowEffect,
        QLabel,
        QPushButton,
        QVBoxLayout,
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

    # Planning has a toolbar and filters as bare layouts. Wrap those two
    # presentation rows in one surface so it follows the Directory language.
    planning_card = None
    planning_page = window.pages.widget(2) if getattr(window, "pages", None) is not None else None
    planning_root = planning_page.layout() if planning_page is not None else None
    month_label = getattr(window, "planning_month_label", None)
    department = getattr(window, "planning_department", None)
    if planning_root is not None and month_label is not None and department is not None:
        toolbar_index = None
        filters_index = None
        for index in range(planning_root.count()):
            item = planning_root.itemAt(index)
            layout = item.layout()
            if layout is None:
                continue
            widgets = []
            for child_index in range(layout.count()):
                child = layout.itemAt(child_index)
                if child.widget() is not None:
                    widgets.append(child.widget())
            if month_label in widgets:
                toolbar_index = index
            if department in widgets:
                filters_index = index

        if toolbar_index is not None and filters_index is not None:
            first, second = sorted((toolbar_index, filters_index))
            second_item = planning_root.takeAt(second)
            first_item = planning_root.takeAt(first)
            first_layout = first_item.layout()
            second_layout = second_item.layout()
            if first_layout is not None and second_layout is not None:
                planning_card = QFrame(planning_page)
                planning_card.setObjectName("planningControlCard")
                card_layout = QVBoxLayout(planning_card)
                card_layout.setContentsMargins(14, 12, 14, 12)
                card_layout.setSpacing(10)
                # Preserve the original visual order, independent of which
                # layout index happened to be lower after other UI adapters.
                toolbar_layout = first_layout if month_label in [
                    first_layout.itemAt(i).widget() for i in range(first_layout.count())
                ] else second_layout
                filter_layout = second_layout if toolbar_layout is first_layout else first_layout
                card_layout.addLayout(toolbar_layout)
                card_layout.addLayout(filter_layout)
                planning_root.insertWidget(first, planning_card)
                month_label.setObjectName("planningMonthLabel")

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

    if planning_card is not None:
        elevation_effects.append(shadow(planning_card, 22, 4, 24))

    def apply_app_visuals() -> None:
        palette = window.theme_manager.palette()
        panel = palette["panel_bg"]
        border = palette["border"]
        text = palette["text"]
        secondary = palette["text_secondary"]
        alternate = palette["alternate_row"]
        hover = palette["hover"]

        if planning_card is not None:
            planning_card.setStyleSheet(
                f"""
                QFrame#planningControlCard {{
                    background: {panel};
                    border: 1px solid {border};
                    border-radius: 12px;
                }}
                QFrame#planningControlCard QLabel {{
                    border: none;
                    background: transparent;
                }}
                QLabel#planningMonthLabel {{
                    color: {text};
                    font-size: 16px;
                    font-weight: 650;
                    padding: 0 4px;
                }}
                """
            )

        # Empty-state labels are intentionally quiet, but centred states should
        # read as deliberate surfaces instead of leftover blank table space.
        for label in window.findChildren(QLabel):
            if label.objectName() == "secondaryText" and label.alignment():
                if label.alignment() & 0x0004:  # Qt.AlignHCenter without importing Qt here.
                    label.setStyleSheet(
                        f"color: {secondary}; background: {alternate}; "
                        f"border: 1px solid {border}; border-radius: 10px; padding: 18px;"
                    )

        for button in app.allWidgets():
            if isinstance(button, QPushButton):
                polish_button(button)

    original_sync = getattr(window, "_sync_theme_controls", None)
    if callable(original_sync):
        def sync_theme() -> None:
            original_sync()
            apply_app_visuals()

        window._sync_theme_controls = sync_theme

    apply_app_visuals()
    window.modern_planning_card = planning_card
    window.modern_app_button_filter = filter_object
    window.modern_app_elevation_effects = elevation_effects
    window.polish_modern_button = polish_button
    window._modern_app_ui_installed = True
