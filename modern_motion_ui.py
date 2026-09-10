"""Visible but restrained motion for the modern PersonnelTracker prototype.

Presentation only. Adds a stronger page reveal, a moving sidebar selection
indicator and a lightweight animated toast. Navigation, clipboard logic and
persistence stay owned by their existing UI/service layers.
"""
from __future__ import annotations

from typing import Any


PAGE_FADE_MS = 230
PAGE_START_OPACITY = 0.35
NAV_INDICATOR_MS = 240
TOAST_IN_MS = 220
TOAST_HOLD_MS = 1400
TOAST_OUT_MS = 220
TOAST_TRAVEL_PX = 20


def install_modern_motion_ui(window: Any) -> None:
    from PySide6.QtCore import (
        QEasingCurve,
        QPoint,
        QPropertyAnimation,
        QRect,
        QTimer,
        Qt,
    )
    from PySide6.QtWidgets import (
        QFrame,
        QGraphicsOpacityEffect,
        QHBoxLayout,
        QLabel,
        QPushButton,
    )

    if getattr(window, "_modern_motion_ui_installed", False):
        return

    pages = getattr(window, "pages", None)
    if pages is None:
        return

    # -------------------- Main page transition ----------------------------
    def animate_current_page(index: int) -> None:
        page = pages.widget(index)
        if page is None or page.graphicsEffect() is not None:
            return

        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(PAGE_START_OPACITY)
        page.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(PAGE_FADE_MS)
        animation.setStartValue(PAGE_START_OPACITY)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def finish() -> None:
            if page.graphicsEffect() is effect:
                page.setGraphicsEffect(None)

        animation.finished.connect(finish)
        window.modern_motion_page_animation = animation

        # Let Qt paint the newly selected page once at the starting opacity.
        # Starting in the next event-loop turn makes the reveal perceptible on
        # fast Macs instead of completing between two visible frames.
        QTimer.singleShot(0, animation.start)

    pages.currentChanged.connect(animate_current_page)

    # -------------------- Moving sidebar indicator ------------------------
    sidebar = getattr(window, "modern_sidebar", None)
    if sidebar is None:
        sidebar = window.findChild(QFrame, "sidebar")

    nav_buttons = list(getattr(window, "modern_sidebar_buttons", []) or [])
    if not nav_buttons:
        group = getattr(window, "nav_group", None)
        if group is not None:
            nav_buttons = [button for button in group.buttons() if not button.isHidden()]

    nav_indicator = None
    nav_animation = None
    if sidebar is not None and nav_buttons:
        nav_indicator = QFrame(sidebar)
        nav_indicator.setObjectName("modernNavIndicator")
        nav_indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        nav_indicator.hide()

        nav_animation = QPropertyAnimation(nav_indicator, b"geometry", sidebar)
        nav_animation.setDuration(NAV_INDICATOR_MS)
        nav_animation.setEasingCurve(QEasingCurve.OutCubic)

        def indicator_rect(button: QPushButton) -> QRect:
            geometry = button.geometry()
            height = max(22, geometry.height() - 14)
            return QRect(4, geometry.y() + 7, 3, height)

        def move_indicator(button: QPushButton, *, animated: bool = True) -> None:
            if nav_indicator is None or button.isHidden():
                return
            target = indicator_rect(button)
            nav_animation.stop()
            if not nav_indicator.isVisible() or not animated:
                nav_indicator.setGeometry(target)
                nav_indicator.show()
            else:
                nav_animation.setStartValue(nav_indicator.geometry())
                nav_animation.setEndValue(target)
                nav_animation.start()
            nav_indicator.raise_()

        for button in nav_buttons:
            button.toggled.connect(
                lambda checked, b=button: move_indicator(b) if checked else None
            )

        def place_initial_indicator() -> None:
            checked = getattr(window, "nav_group", None)
            checked = checked.checkedButton() if checked is not None else None
            if checked is not None and not checked.isHidden():
                move_indicator(checked, animated=False)

        QTimer.singleShot(0, place_initial_indicator)

    # -------------------- Small non-blocking toast ------------------------
    central = window.centralWidget()
    toast = QFrame(central)
    toast.setObjectName("modernToast")
    toast.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    toast.hide()
    toast_layout = QHBoxLayout(toast)
    toast_layout.setContentsMargins(14, 9, 14, 9)
    toast_layout.setSpacing(7)
    toast_mark = QLabel("✓", toast)
    toast_mark.setObjectName("modernToastMark")
    toast_text = QLabel("Скопировано", toast)
    toast_text.setObjectName("modernToastText")
    toast_layout.addWidget(toast_mark)
    toast_layout.addWidget(toast_text)

    toast_effect = QGraphicsOpacityEffect(toast)
    toast_effect.setOpacity(0.0)
    toast.setGraphicsEffect(toast_effect)

    toast_in = QPropertyAnimation(toast_effect, b"opacity", toast)
    toast_in.setDuration(TOAST_IN_MS)
    toast_in.setStartValue(0.0)
    toast_in.setEndValue(1.0)
    toast_in.setEasingCurve(QEasingCurve.OutCubic)

    toast_move = QPropertyAnimation(toast, b"pos", toast)
    toast_move.setDuration(TOAST_IN_MS)
    toast_move.setEasingCurve(QEasingCurve.OutCubic)

    toast_out = QPropertyAnimation(toast_effect, b"opacity", toast)
    toast_out.setDuration(TOAST_OUT_MS)
    toast_out.setStartValue(1.0)
    toast_out.setEndValue(0.0)
    toast_out.setEasingCurve(QEasingCurve.InCubic)
    toast_out.finished.connect(toast.hide)

    toast_timer = QTimer(toast)
    toast_timer.setSingleShot(True)
    toast_timer.setInterval(TOAST_HOLD_MS)
    toast_timer.timeout.connect(toast_out.start)

    def apply_motion_style() -> None:
        palette = window.theme_manager.palette()
        panel = palette["panel_bg"]
        text = palette["text"]
        border = palette["border"]
        success = palette["success"]
        accent = palette["accent"]
        toast.setStyleSheet(
            f"""
            QFrame#modernToast {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 11px;
            }}
            QLabel#modernToastMark {{
                color: {success};
                border: none;
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#modernToastText {{
                color: {text};
                border: none;
                font-size: 12px;
                font-weight: 600;
            }}
            """
        )
        if nav_indicator is not None:
            nav_indicator.setStyleSheet(
                f"QFrame#modernNavIndicator {{ background: {accent}; border: none; border-radius: 2px; }}"
            )

    def place_toast() -> tuple[QPoint, QPoint]:
        toast.adjustSize()
        margin = 24
        end = QPoint(
            max(margin, central.width() - toast.width() - margin),
            max(margin, central.height() - toast.height() - margin),
        )
        start = QPoint(end.x(), end.y() + TOAST_TRAVEL_PX)
        return start, end

    def show_toast(text: str = "Скопировано") -> None:
        toast_timer.stop()
        toast_out.stop()
        toast_in.stop()
        toast_move.stop()
        toast_text.setText(text)
        start, end = place_toast()
        toast.move(start)
        toast.raise_()
        toast_effect.setOpacity(0.0)
        toast.show()
        toast_move.setStartValue(start)
        toast_move.setEndValue(end)
        toast_in.start()
        toast_move.start()
        toast_timer.start()

    directory = getattr(window, "composition_directory", None)
    table = getattr(window, "composition_directory_table", None)
    copy_button = None
    if directory is not None:
        copy_button = next(
            (button for button in directory.findChildren(QPushButton) if button.text() == "Копировать"),
            None,
        )

    def copy_feedback() -> None:
        # The existing copy handler remains authoritative. This second slot only
        # acknowledges a successful-looking action when a selection exists.
        if table is not None and table.selectedIndexes():
            show_toast("Скопировано")

    if copy_button is not None:
        copy_button.clicked.connect(copy_feedback)

    original_sync = getattr(window, "_sync_theme_controls", None)
    if callable(original_sync):
        def sync_theme() -> None:
            original_sync()
            apply_motion_style()

        window._sync_theme_controls = sync_theme

    apply_motion_style()
    window.modern_motion_toast = toast
    window.modern_motion_toast_effect = toast_effect
    window.modern_motion_toast_timer = toast_timer
    window.modern_motion_nav_indicator = nav_indicator
    window.modern_motion_nav_animation = nav_animation
    window.show_modern_toast = show_toast
    window.modern_motion_page_animation = None
    window._modern_motion_ui_installed = True
