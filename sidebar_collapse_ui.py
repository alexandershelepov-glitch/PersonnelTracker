"""Persistent collapsible sidebar for a wider working area.

Presentation only. Keeps the existing navigation and page structure intact.
"""
from __future__ import annotations

from typing import Any


def install_sidebar_collapse_ui(window: Any) -> None:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QLabel, QMenu, QPushButton

    if getattr(window, "_sidebar_collapse_ui_installed", False):
        return

    sidebar = getattr(window, "modern_sidebar", None)
    buttons = list(getattr(window, "modern_sidebar_buttons", []))
    if sidebar is None or not buttons:
        return

    layout = sidebar.layout()
    if layout is None:
        return

    labels = [
        label for label in sidebar.findChildren(QLabel)
        if label.objectName() in {"appTitle", "appSubtitle"}
    ]
    button_labels = {
        button: str(button.property("modernNavLabel") or button.text())
        for button in buttons
    }

    toggle = QPushButton("‹  Свернуть", sidebar)
    toggle.setObjectName("sidebarCollapseButton")
    toggle.setToolTip("Свернуть боковую панель")
    toggle.setMinimumHeight(32)

    insert_at = layout.count()
    for index in range(layout.count()):
        if layout.itemAt(index).spacerItem() is not None:
            insert_at = index
            break
    layout.insertWidget(insert_at, toggle)

    view_menu = None
    for action in window.menuBar().actions():
        menu = action.menu()
        if isinstance(menu, QMenu) and menu.title() == "Вид":
            view_menu = menu
            break
    if view_menu is None:
        view_menu = window.menuBar().addMenu("Вид")

    toggle_action = QAction("Свернуть боковую панель", window)
    view_menu.addAction(toggle_action)

    expanded_min = 196
    expanded_max = 224
    collapsed_width = 62

    def stored_collapsed() -> bool:
        raw = window.settings.value("ui/sidebar_collapsed", False)
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def apply_state(collapsed: bool, *, persist: bool = True) -> None:
        sidebar.setProperty("collapsed", collapsed)
        if collapsed:
            sidebar.setMinimumWidth(collapsed_width)
            sidebar.setMaximumWidth(collapsed_width)
        else:
            sidebar.setMinimumWidth(expanded_min)
            sidebar.setMaximumWidth(expanded_max)

        for label in labels:
            label.setVisible(not collapsed)

        for button, label in button_labels.items():
            button.setText("" if collapsed else label)
            button.setToolTip(label if collapsed else "")
            button.setAccessibleName(label)
            if collapsed:
                button.setStyleSheet("text-align: center; padding-left: 0px; padding-right: 0px;")
            else:
                button.setStyleSheet("")

        toggle.setText("›" if collapsed else "‹  Свернуть")
        toggle.setToolTip("Развернуть боковую панель" if collapsed else "Свернуть боковую панель")
        toggle_action.setText("Развернуть боковую панель" if collapsed else "Свернуть боковую панель")

        if collapsed:
            toggle.setStyleSheet("text-align: center; padding-left: 0px; padding-right: 0px;")
        else:
            toggle.setStyleSheet("")

        sidebar.style().unpolish(sidebar)
        sidebar.style().polish(sidebar)
        sidebar.updateGeometry()

        if persist:
            window.settings.setValue("ui/sidebar_collapsed", collapsed)

        window.sidebar_collapsed = collapsed

    def switch_state() -> None:
        apply_state(not bool(getattr(window, "sidebar_collapsed", False)))

    toggle.clicked.connect(switch_state)
    toggle_action.triggered.connect(switch_state)

    apply_state(stored_collapsed(), persist=False)

    window.sidebar_collapse_button = toggle
    window.sidebar_collapse_action = toggle_action
    window.set_sidebar_collapsed = apply_state
    window._sidebar_collapse_ui_installed = True
