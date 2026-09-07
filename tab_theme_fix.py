"""Theme-safe tab styling for the v0.8.3 interface.

Qt/macOS document-mode tabs can partially fall back to native colours and
produce a light tab strip inside the dark application theme. This adapter keeps
all tab widgets on the application's own palette and does not alter workflow or
data logic.
"""
from __future__ import annotations

from typing import Any


def install_tab_theme_fix(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTabWidget

    if getattr(window, "_tab_theme_fix_installed", False):
        return

    def style_tabs(tabs: QTabWidget) -> None:
        palette = window.theme_manager.palette()
        tabs.setDocumentMode(False)
        bar = tabs.tabBar()
        bar.setDrawBase(False)
        bar.setUsesScrollButtons(True)
        bar.setElideMode(Qt.ElideRight)
        tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: 1px solid {palette['border']};
                background: {palette['window_bg']};
            }}
            QTabBar {{
                background: {palette['window_bg']};
            }}
            QTabBar::tab {{
                background: {palette['window_bg']};
                color: {palette['text_secondary']};
                padding: 8px 14px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {palette['accent']};
                background: {palette['window_bg']};
                border-bottom: 2px solid {palette['accent']};
                font-weight: 600;
            }}
            QTabBar::tab:hover:!selected {{
                color: {palette['text']};
                background: {palette['hover']};
            }}
            """
        )

    def style_existing_tabs() -> None:
        for tabs in window.findChildren(QTabWidget):
            style_tabs(tabs)

    # Employee profiles are created lazily after the main window is ready.
    profile_class = getattr(window, "employee_profile_dialog_class", None)
    if profile_class is not None and not getattr(profile_class, "_v083_tab_theme_fixed", False):
        original_profile_init = profile_class.__init__

        def profile_init(dialog, *args, **kwargs):
            original_profile_init(dialog, *args, **kwargs)
            for tabs in dialog.findChildren(QTabWidget):
                style_tabs(tabs)

        profile_class.__init__ = profile_init
        profile_class._v083_tab_theme_fixed = True

    original_sync = window._sync_theme_controls

    def sync_theme() -> None:
        original_sync()
        style_existing_tabs()

    window._sync_theme_controls = sync_theme
    style_existing_tabs()
    window._tab_theme_fix_installed = True
