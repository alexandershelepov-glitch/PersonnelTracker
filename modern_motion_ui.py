"""Restrained motion layer for the modern PersonnelTracker prototype.

Presentation only. Adds short page fades and a lightweight animated toast for
successful Directory copying. Navigation, clipboard logic and persistence stay
owned by their existing UI/service layers.
"""
from __future__ import annotations

from typing import Any


PAGE_FADE_MS = 150
TOAST_IN_MS = 160
TOAST_HOLD_MS = 1200
TOAST_OUT_MS = 180


def install_modern_motion_ui(window: Any) -> None:
    from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
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
        effect.setOpacity(0.84)
        page.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(PAGE_FADE_MS)
        animation.setStartValue(0.84)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def finish() -> None:
            if page.graphicsEffect() is effect:
                page.setGraphicsEffect(None)

        animation.finished.connect(finish)
        window.modern_motion_page_animation = animation
        animation.start()

    pages.currentChanged.connect(animate_current_page)

    # -------------------- Small non-blocking toast ------------------------
    central = window.centralWidget()
    toast = QFrame(central)
    toast.setObjectName("modernToast")
    toast.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    toast.hide()
    toast_layout = QHBoxLayout(toast)
    toast_layout.setContentsMargins(13, 8, 13, 8)
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

    def apply_toast_style() -> None:
        palette = window.theme_manager.palette()
        panel = palette["panel_bg"]
        text = palette["text"]
        secondary = palette["text_secondary"]
        border = palette["border"]
        success = palette["success"]
        toast.setStyleSheet(
            f"""
            QFrame#modernToast {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 10px;
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
        toast_text.setToolTip(f"Уведомление исчезнет автоматически")
        toast_mark.setToolTip(secondary)

    def place_toast() -> tuple[QPoint, QPoint]:
        toast.adjustSize()
        margin = 24
        end = QPoint(
            max(margin, central.width() - toast.width() - margin),
            max(margin, central.height() - toast.height() - margin),
        )
        start = QPoint(end.x(), end.y() + 8)
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
            apply_toast_style()

        window._sync_theme_controls = sync_theme

    apply_toast_style()
    window.modern_motion_toast = toast
    window.modern_motion_toast_effect = toast_effect
    window.modern_motion_toast_timer = toast_timer
    window.show_modern_toast = show_toast
    window.modern_motion_page_animation = None
    window._modern_motion_ui_installed = True
