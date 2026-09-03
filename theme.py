"""Централизованная визуальная система приложения (v0.6).

Все цвета, отступы и радиусы живут в палитрах LIGHT_PALETTE / DARK_PALETTE.
Виджеты не задают случайные стили сами: им назначаются objectName или
динамическое свойство (например ``role="primary"``), а итоговый вид
определяется единой QSS-таблицей, построенной из палитры.

Семантические цвета (вакансия, просроченный контроль и т.п.) доступны из кода
через :meth:`ThemeManager.color`, чтобы таблицы красились теми же токенами,
что и остальная тема.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


# --- Токены оформления ------------------------------------------------------

_COMMON = {
    "radius": "6px",
    "radius_large": "10px",
    "padding": "6px 10px",
    "spacing": "8px",
}

LIGHT_PALETTE = {
    "window_bg": "#f4f6f9",
    "panel_bg": "#ffffff",
    "sidebar_bg": "#e9edf3",
    "sidebar_hover": "#dde4ee",
    "sidebar_active": "#2f6fed",
    "sidebar_active_text": "#ffffff",
    "text": "#1f2937",
    "text_secondary": "#64748b",
    "border": "#d3dae3",
    "hover": "#e8f0fe",
    "selected": "#2f6fed",
    "selected_text": "#ffffff",
    "accent": "#2f6fed",
    "accent_hover": "#255fd0",
    "accent_text": "#ffffff",
    "success": "#2e7d32",
    "warning": "#b45309",
    "warning_bg": "#fdf3e0",
    "error": "#c62828",
    "error_bg": "#fde8e8",
    "vacancy_bg": "#fdf3e0",
    "vacancy_text": "#8a5a00",
    "attention_bg": "#fde8e8",
    "muted": "#94a3b8",
    "header_bg": "#eef1f6",
    "alternate_row": "#f8fafc",
}

DARK_PALETTE = {
    "window_bg": "#1c1f26",
    "panel_bg": "#262a33",
    "sidebar_bg": "#22262f",
    "sidebar_hover": "#2c313d",
    "sidebar_active": "#4a82f0",
    "sidebar_active_text": "#ffffff",
    "text": "#e5e7eb",
    "text_secondary": "#9aa4b2",
    "border": "#3d434f",
    "hover": "#303845",
    "selected": "#4a82f0",
    "selected_text": "#ffffff",
    "accent": "#4a82f0",
    "accent_hover": "#6090f5",
    "accent_text": "#ffffff",
    "success": "#66bb6a",
    "warning": "#e0a44a",
    "warning_bg": "#3a2f1c",
    "error": "#ef5350",
    "error_bg": "#402626",
    "vacancy_bg": "#3a2f1c",
    "vacancy_text": "#e0a44a",
    "attention_bg": "#402626",
    "muted": "#6b7280",
    "header_bg": "#2c313d",
    "alternate_row": "#232833",
}


def _stylesheet(p: dict[str, str]) -> str:
    """Собрать QSS целиком из палитры — ни одного литерального цвета."""
    return f"""
        QWidget {{ color: {p['text']}; font-size: 13px; }}
        QMainWindow, QDialog {{ background: {p['window_bg']}; }}
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}

        /* --- Боковая навигация --- */
        QFrame#sidebar {{
            background: {p['sidebar_bg']};
            border-right: 1px solid {p['border']};
        }}
        QLabel#appTitle {{
            font-size: 15px; font-weight: 700; padding: 14px 14px 6px 14px;
        }}
        QLabel#appSubtitle {{
            color: {p['text_secondary']}; font-size: 11px; padding: 0 14px 10px 14px;
        }}
        QPushButton[navButton="true"] {{
            background: transparent; border: none; border-radius: {_COMMON['radius']};
            padding: 9px 14px; text-align: left; color: {p['text']};
        }}
        QPushButton[navButton="true"]:hover {{ background: {p['sidebar_hover']}; }}
        QPushButton[navButton="true"]:checked {{
            background: {p['sidebar_active']}; color: {p['sidebar_active_text']}; font-weight: 600;
        }}

        /* --- Заголовки страниц и карточки показателей --- */
        QLabel#pageTitle {{ font-size: 18px; font-weight: 700; }}
        QFrame#metricCard {{
            background: {p['panel_bg']}; border: 1px solid {p['border']};
            border-radius: {_COMMON['radius_large']};
        }}
        QLabel#metricValue {{ font-size: 20px; font-weight: 700; }}
        QLabel#metricCaption {{ color: {p['text_secondary']}; font-size: 12px; }}
        QLabel#secondaryText {{ color: {p['text_secondary']}; }}
        QLabel#warningText {{ color: {p['error']}; font-weight: 600; }}

        /* --- Группы и панели --- */
        QGroupBox {{
            background: {p['panel_bg']}; border: 1px solid {p['border']};
            border-radius: {_COMMON['radius_large']}; margin-top: 14px; padding: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 10px; padding: 0 4px; color: {p['text']}; font-weight: 600;
        }}

        /* --- Поля ввода --- */
        QLineEdit, QComboBox, QDateEdit, QSpinBox, QTextEdit {{
            background: {p['panel_bg']}; color: {p['text']};
            border: 1px solid {p['border']}; border-radius: {_COMMON['radius']};
            padding: 5px 8px; selection-background-color: {p['selected']};
            selection-color: {p['selected_text']};
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QTextEdit:focus {{
            border: 1px solid {p['accent']};
        }}
        QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{
            color: {p['text_secondary']}; background: {p['alternate_row']};
        }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox QAbstractItemView {{
            background: {p['panel_bg']}; color: {p['text']};
            border: 1px solid {p['border']};
            selection-background-color: {p['selected']}; selection-color: {p['selected_text']};
        }}
        QDateEdit::up-button, QDateEdit::down-button,
        QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; }}

        /* --- Кнопки --- */
        QPushButton {{
            background: {p['panel_bg']}; color: {p['text']};
            border: 1px solid {p['border']}; border-radius: {_COMMON['radius']};
            padding: {_COMMON['padding']};
        }}
        QPushButton:hover {{ background: {p['hover']}; }}
        QPushButton:pressed {{ background: {p['selected']}; color: {p['selected_text']}; }}
        QPushButton:disabled {{ color: {p['muted']}; background: {p['alternate_row']}; }}
        QPushButton[role="primary"] {{
            background: {p['accent']}; color: {p['accent_text']};
            border: none; font-weight: 600; padding: 7px 16px;
        }}
        QPushButton[role="primary"]:hover {{ background: {p['accent_hover']}; }}
        QPushButton[role="primary"]:pressed {{ background: {p['accent']}; }}
        QPushButton[role="danger"]:hover {{ background: {p['error_bg']}; border-color: {p['error']}; }}

        QToolButton {{
            background: {p['panel_bg']}; color: {p['text']};
            border: 1px solid {p['border']}; border-radius: {_COMMON['radius']};
            padding: {_COMMON['padding']};
        }}
        QToolButton:hover {{ background: {p['hover']}; }}
        QToolButton::menu-indicator {{ image: none; width: 0; }}

        /* --- Таблицы и деревья --- */
        QTableWidget, QTreeWidget {{
            background: {p['panel_bg']}; color: {p['text']};
            alternate-background-color: {p['alternate_row']};
            border: 1px solid {p['border']}; border-radius: {_COMMON['radius']};
            gridline-color: {p['border']};
            selection-background-color: {p['selected']}; selection-color: {p['selected_text']};
        }}
        QTableWidget::item:selected, QTreeWidget::item:selected {{
            background: {p['selected']}; color: {p['selected_text']};
        }}
        QTableWidget::item:hover, QTreeWidget::item:hover {{ background: {p['hover']}; }}
        QHeaderView {{ background: {p['header_bg']}; }}
        QHeaderView::section {{
            background: {p['header_bg']}; color: {p['text']};
            padding: 6px 8px; border: none;
            border-right: 1px solid {p['border']}; border-bottom: 1px solid {p['border']};
            font-weight: 600;
        }}
        QTableCornerButton::section {{
            background: {p['header_bg']}; border: none; border-bottom: 1px solid {p['border']};
        }}

        /* --- Вкладки (внутренние, например в карточке работника) --- */
        QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: {_COMMON['radius']}; background: {p['window_bg']}; }}
        QTabBar::tab {{
            background: transparent; color: {p['text_secondary']};
            padding: 8px 14px; border: none; border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:selected {{ color: {p['accent']}; border-bottom: 2px solid {p['accent']}; font-weight: 600; }}
        QTabBar::tab:hover:!selected {{ color: {p['text']}; background: {p['hover']}; }}

        /* --- Меню --- */
        QMenuBar {{ background: {p['window_bg']}; color: {p['text']}; border-bottom: 1px solid {p['border']}; }}
        QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
        QMenuBar::item:selected {{ background: {p['hover']}; border-radius: {_COMMON['radius']}; }}
        QMenu {{
            background: {p['panel_bg']}; color: {p['text']}; border: 1px solid {p['border']};
            padding: 4px;
        }}
        QMenu::item {{ padding: 6px 24px 6px 20px; border-radius: {_COMMON['radius']}; }}
        QMenu::item:selected {{ background: {p['selected']}; color: {p['selected_text']}; }}
        QMenu::separator {{ height: 1px; background: {p['border']}; margin: 4px 8px; }}

        /* --- Диалоги и сообщения --- */
        QMessageBox QLabel {{ color: {p['text']}; }}
        QDialogButtonBox QPushButton {{ min-width: 90px; }}

        /* --- Прокрутка --- */
        QScrollBar:vertical {{
            background: transparent; width: 12px; margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {p['border']}; border-radius: 5px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent; height: 12px; margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p['border']}; border-radius: 5px; min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {p['muted']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        /* --- Фото-заглушка в карточке --- */
        QLabel#photoFrame {{
            border: 1px solid {p['border']}; border-radius: {_COMMON['radius']};
            background: {p['alternate_row']}; color: {p['muted']};
        }}

        QToolTip {{
            background: {p['panel_bg']}; color: {p['text']};
            border: 1px solid {p['border']}; padding: 4px 8px;
        }}
        QStatusBar {{ background: {p['window_bg']}; color: {p['text_secondary']}; }}
    """


class ThemeManager:
    """Единая точка управления темами приложения.

    Хранит выбор пользователя в ``QSettings``, строит QSS из палитры и
    выдаёт семантические цвета для программной раскраски ячеек таблиц."""

    SETTINGS_KEY = "appearance/theme"
    LIGHT = "light"
    DARK = "dark"

    def __init__(self, settings: QSettings | None = None):
        self.settings = settings or QSettings("PersonnelTracker", "PersonnelTracker")
        self._theme = self.current_theme()

    # --- темы ---------------------------------------------------------------
    def current_theme(self) -> str:
        value = str(self.settings.value(self.SETTINGS_KEY, self.LIGHT))
        return value if value in {self.LIGHT, self.DARK} else self.LIGHT

    def apply(self, app: QApplication, theme: str | None = None) -> str:
        selected = theme or self.current_theme()
        selected = selected if selected in {self.LIGHT, self.DARK} else self.LIGHT
        self._theme = selected
        app.setStyleSheet(_stylesheet(self.palette()))
        self.settings.setValue(self.SETTINGS_KEY, selected)
        return selected

    def toggle(self, app: QApplication) -> str:
        next_theme = self.DARK if self._theme == self.LIGHT else self.LIGHT
        return self.apply(app, next_theme)

    # --- токены ---------------------------------------------------------------
    def palette(self) -> dict[str, str]:
        return dict(DARK_PALETTE if self._theme == self.DARK else LIGHT_PALETTE)

    def color(self, role: str) -> QColor:
        """Семантический цвет текущей темы для программной раскраски.

        Используется таблицей ШДС (вакансии, просроченный контроль) и другими
        местами, где QSS недоступен.  Неизвестная роль — обычный текст."""
        return QColor(self.palette().get(role, self.palette()["text"]))
