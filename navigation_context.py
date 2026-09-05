"""Context-aware Back navigation for the v0.8.3 workflow.

The four sidebar sections are roots only when the user enters them from the
sidebar.  The same screen may also be opened from another working context
(e.g. Today -> detailed state -> Planning); in that case Back must remain
available and return to the actual caller.
"""
from __future__ import annotations

from typing import Any


def install_context_navigation(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    if getattr(window, "_context_navigation_installed", False):
        return
    if not hasattr(window, "today_page") or not hasattr(window, "_navigation_stack"):
        return

    today_index = window.pages.indexOf(window.today_page)
    original_select = window._select_page

    # Reuse Back buttons already created for legacy nested pages and add the
    # same affordance to root pages.  Their visibility is context-dependent:
    # sidebar entry hides Back; contextual entry shows it.
    back_buttons: dict[int, QPushButton] = {}
    existing = getattr(window, "_nested_back_buttons", {})
    for index, button in existing.items():
        back_buttons[int(index)] = button

    for index in range(window.pages.count()):
        if index == today_index or index in back_buttons:
            continue
        page = window.pages.widget(index)
        layout = page.layout() if page is not None else None
        if layout is None:
            continue
        button = QPushButton("← Назад")
        layout.insertWidget(0, button, 0, Qt.AlignLeft)
        back_buttons[index] = button

    def update_back_buttons() -> None:
        current = window.pages.currentIndex()
        has_history = bool(window._navigation_stack)
        for index, button in back_buttons.items():
            button.setVisible(has_history and current == index)

    def select(index: int, record_history: bool = True) -> None:
        current = window.pages.currentIndex()
        if record_history and current != index:
            if not window._navigation_stack or window._navigation_stack[-1] != current:
                window._navigation_stack.append(current)
        # The previous v0.8.3 wrapper knows how to keep the parent sidebar
        # button checked.  We disable its own history recording to avoid a
        # duplicate stack entry.
        original_select(index, record_history=False)
        update_back_buttons()

    def navigate_back() -> None:
        target = window._navigation_stack.pop() if window._navigation_stack else today_index
        original_select(target, record_history=False)
        update_back_buttons()

    window._select_page = select
    window.navigate_back = navigate_back
    window._context_back_buttons = back_buttons

    # Existing buttons were connected to the first navigation wrapper. Replace
    # those callbacks so every Back action uses the same context stack.
    for button in back_buttons.values():
        try:
            button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        button.clicked.connect(navigate_back)

    # Sidebar buttons already call navigate_root() inside today_ui, which
    # clears the stack. Add a final visibility refresh after that callback.
    for button in window.nav_group.buttons():
        if not button.isHidden():
            button.clicked.connect(lambda _checked=False: update_back_buttons())

    update_back_buttons()
    window._context_navigation_installed = True
