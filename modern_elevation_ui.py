"""Subtle elevation layer for the modern Composition directory.

Presentation only: adds restrained drop shadows and an elevated empty-state
surface without changing any directory behaviour, data or services.
"""
from __future__ import annotations

from typing import Any


def install_modern_elevation_ui(window: Any) -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    if getattr(window, "_modern_elevation_ui_installed", False):
        return

    toolbar = getattr(window, "modern_directory_toolbar", None)
    table = getattr(window, "composition_directory_table", None)
    empty_state = getattr(window, "composition_empty_state", None)
    if toolbar is None or table is None or empty_state is None:
        return

    def shadow(widget, *, blur: float, y: float, alpha: int):
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(0, y)
        effect.setColor(QColor(15, 23, 42, alpha))
        widget.setGraphicsEffect(effect)
        return effect

    # Strongest elevation belongs to the filter/search surface; the table is
    # intentionally flatter so dense personnel data remains the visual focus.
    toolbar_shadow = shadow(toolbar, blur=28, y=5, alpha=42)
    table_shadow = shadow(table, blur=18, y=3, alpha=24)
    empty_shadow = shadow(empty_state, blur=24, y=4, alpha=32)

    def apply_elevation_style() -> None:
        palette = window.theme_manager.palette()
        panel = palette["panel_bg"]
        border = palette["border"]
        secondary = palette["text_secondary"]

        empty_state.setStyleSheet(
            f"""
            QLabel#directoryEmptyState {{
                background: {panel};
                color: {secondary};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 32px;
                font-size: 14px;
            }}
            """
        )

    original_sync = getattr(window, "_sync_theme_controls", None)
    if callable(original_sync):
        def sync_theme() -> None:
            original_sync()
            apply_elevation_style()

        window._sync_theme_controls = sync_theme

    apply_elevation_style()
    window.modern_directory_toolbar_shadow = toolbar_shadow
    window.modern_directory_table_shadow = table_shadow
    window.modern_directory_empty_shadow = empty_shadow
    window._modern_elevation_ui_installed = True
