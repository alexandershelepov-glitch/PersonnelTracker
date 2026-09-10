"""Central visual system for PersonnelTracker.

Colours, radii and widget treatment live here so every workflow, report and
child dialog shares one calm desktop design. Business and data semantics use
the same named colour roles through ThemeManager.color().
"""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


_COMMON = {
    "radius": "8px",
    "radius_large": "12px",
    "padding": "7px 11px",
    "spacing": "8px",
}

LIGHT_PALETTE = {
    "window_bg": "#f5f7fb",
    "panel_bg": "#ffffff",
    "sidebar_bg": "#f5f7fb",
    "sidebar_hover": "#eef1f6",
    "sidebar_active": "#4169e1",
    "sidebar_active_text": "#ffffff",
    "text": "#172033",
    "text_secondary": "#667085",
    "border": "#e3e8ef",
    "hover": "#eef2ff",
    "selected": "#4169e1",
    "selected_text": "#ffffff",
    "accent": "#4169e1",
    "accent_hover": "#3658c9",
    "accent_text": "#ffffff",
    "success": "#2f7d61",
    "warning": "#b7791f",
    "warning_bg": "#fff7e8",
    "error": "#c94a4a",
    "error_bg": "#fff0f0",
    "vacancy_bg": "#fff7e8",
    "vacancy_text": "#97651a",
    "attention_bg": "#fff0f0",
    "muted": "#98a2b3",
    "header_bg": "#f7f9fc",
    "alternate_row": "#fafbfc",
}

DARK_PALETTE = {
    "window_bg": "#171a21",
    "panel_bg": "#20242d",
    "sidebar_bg": "#171a21",
    "sidebar_hover": "#252a34",
    "sidebar_active": "#6f8ff8",
    "sidebar_active_text": "#ffffff",
    "text": "#e7eaf0",
    "text_secondary": "#98a2b3",
    "border": "#343a46",
    "hover": "#293247",
    "selected": "#6f8ff8",
    "selected_text": "#ffffff",
    "accent": "#6f8ff8",
    "accent_hover": "#86a0fb",
    "accent_text": "#ffffff",
    "success": "#69b99a",
    "warning": "#d6a75b",
    "warning_bg": "#332b1f",
    "error": "#e87878",
    "error_bg": "#382426",
    "vacancy_bg": "#332b1f",
    "vacancy_text": "#d6a75b",
    "attention_bg": "#382426",
    "muted": "#697386",
    "header_bg": "#252a34",
    "alternate_row": "#1c2028",
}


def _stylesheet(p: dict[str, str]) -> str:
    """Build the complete QSS from semantic palette tokens."""
    return f"""
        QWidget {{
            color: {p['text']};
            font-size: 13px;
        }}
        QMainWindow, QDialog {{
            background: {p['window_bg']};
        }}
        QScrollArea, QScrollArea > QWidget > QWidget {{
            background: transparent;
            border: none;
        }}

        /* Sidebar base; the modern chrome layer adds icons and active motion. */
        QFrame#sidebar {{
            background: {p['sidebar_bg']};
            border: none;
            border-right: 1px solid {p['border']};
        }}
        QLabel#appTitle {{
            font-size: 16px;
            font-weight: 700;
            padding: 16px 13px 3px 13px;
        }}
        QLabel#appSubtitle {{
            color: {p['text_secondary']};
            font-size: 11px;
            padding: 0 13px 11px 13px;
        }}
        QPushButton[navButton="true"] {{
            background: transparent;
            border: none;
            border-radius: 9px;
            padding: 9px 12px;
            text-align: left;
            color: {p['text_secondary']};
        }}
        QPushButton[navButton="true"]:hover {{
            background: {p['sidebar_hover']};
            color: {p['text']};
        }}
        QPushButton[navButton="true"]:checked {{
            background: {p['hover']};
            color: {p['accent']};
            font-weight: 600;
        }}

        /* Type hierarchy and dashboard surfaces. */
        QLabel#pageTitle {{
            font-size: 21px;
            font-weight: 700;
            padding: 1px 0 2px 0;
        }}
        QLabel#secondaryText {{
            color: {p['text_secondary']};
        }}
        QLabel#warningText {{
            color: {p['error']};
            font-weight: 600;
        }}
        QLabel#metricValue {{
            font-size: 23px;
            font-weight: 700;
        }}
        QLabel#metricCaption {{
            color: {p['text_secondary']};
            font-size: 12px;
            font-weight: 500;
        }}
        QLabel#todayDate {{
            font-size: 15px;
            font-weight: 600;
        }}
        QLabel#todaySectionTitle {{
            font-size: 14px;
            font-weight: 650;
        }}
        QFrame#metricCard,
        QFrame#todayMetric,
        QFrame#todaySection {{
            background: {p['panel_bg']};
            border: 1px solid {p['border']};
            border-radius: {_COMMON['radius_large']};
        }}
        QFrame#todayMetric {{
            padding: 2px;
        }}

        /* Group boxes are cards rather than heavy framed forms. */
        QGroupBox {{
            background: {p['panel_bg']};
            border: 1px solid {p['border']};
            border-radius: {_COMMON['radius_large']};
            margin-top: 14px;
            padding: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 11px;
            padding: 0 5px;
            color: {p['text']};
            font-weight: 600;
        }}

        /* Inputs. */
        QLineEdit, QComboBox, QDateEdit, QSpinBox, QTextEdit, QPlainTextEdit {{
            background: {p['panel_bg']};
            color: {p['text']};
            border: 1px solid {p['border']};
            border-radius: {_COMMON['radius']};
            padding: 6px 9px;
            selection-background-color: {p['selected']};
            selection-color: {p['selected_text']};
        }}
        QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover,
        QTextEdit:hover, QPlainTextEdit:hover {{
            border-color: {p['muted']};
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
        QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {p['accent']};
        }}
        QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
        QSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            color: {p['text_secondary']};
            background: {p['alternate_row']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background: {p['panel_bg']};
            color: {p['text']};
            border: 1px solid {p['border']};
            selection-background-color: {p['hover']};
            selection-color: {p['text']};
            outline: none;
        }}
        QDateEdit::up-button, QDateEdit::down-button,
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 18px;
        }}

        /* Buttons. */
        QPushButton {{
            background: {p['panel_bg']};
            color: {p['text']};
            border: 1px solid {p['border']};
            border-radius: {_COMMON['radius']};
            padding: {_COMMON['padding']};
            min-height: 18px;
        }}
        QPushButton:hover {{
            background: {p['hover']};
            border-color: {p['muted']};
        }}
        QPushButton:pressed {{
            background: {p['alternate_row']};
        }}
        QPushButton:disabled {{
            color: {p['muted']};
            background: {p['alternate_row']};
            border-color: {p['border']};
        }}
        QPushButton[role="primary"] {{
            background: {p['accent']};
            color: {p['accent_text']};
            border: 1px solid {p['accent']};
            font-weight: 600;
            padding: 7px 15px;
        }}
        QPushButton[role="primary"]:hover {{
            background: {p['accent_hover']};
            border-color: {p['accent_hover']};
        }}
        QPushButton[role="primary"]:pressed {{
            background: {p['accent']};
        }}
        QPushButton[role="danger"] {{
            color: {p['error']};
        }}
        QPushButton[role="danger"]:hover {{
            background: {p['error_bg']};
            border-color: {p['error']};
        }}
        QPushButton[attentionButton="true"] {{
            text-align: left;
            background: {p['warning_bg']};
            border-color: {p['border']};
        }}
        QPushButton[attentionButton="true"]:hover {{
            border-color: {p['warning']};
        }}
        QToolButton {{
            background: {p['panel_bg']};
            color: {p['text']};
            border: 1px solid {p['border']};
            border-radius: {_COMMON['radius']};
            padding: {_COMMON['padding']};
        }}
        QToolButton:hover {{ background: {p['hover']}; }}
        QToolButton::menu-indicator {{ image: none; width: 0; }}

        /* Tables remain dense, but borders and headers are quieter. */
        QTableWidget, QTreeWidget, QTableView, QTreeView {{
            background: {p['panel_bg']};
            color: {p['text']};
            alternate-background-color: {p['alternate_row']};
            border: 1px solid {p['border']};
            border-radius: 10px;
            gridline-color: {p['border']};
            selection-background-color: {p['selected']};
            selection-color: {p['selected_text']};
            outline: none;
        }}
        QTableWidget::item, QTreeWidget::item,
        QTableView::item, QTreeView::item {{
            padding: 4px 7px;
        }}
        QTableWidget::item:hover, QTreeWidget::item:hover,
        QTableView::item:hover, QTreeView::item:hover {{
            background: {p['hover']};
            color: {p['text']};
        }}
        QHeaderView {{
            background: {p['header_bg']};
        }}
        QHeaderView::section {{
            background: {p['header_bg']};
            color: {p['text_secondary']};
            padding: 7px 9px;
            border: none;
            border-right: 1px solid {p['border']};
            border-bottom: 1px solid {p['border']};
            font-weight: 600;
        }}
        QTableCornerButton::section {{
            background: {p['header_bg']};
            border: none;
            border-bottom: 1px solid {p['border']};
        }}

        /* Tabs use a soft segmented treatment throughout the app. */
        QTabWidget::pane {{
            border: none;
            background: transparent;
            top: -1px;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {p['text_secondary']};
            padding: 7px 12px;
            margin: 0 3px 5px 0;
            border: none;
            border-radius: 8px;
            min-height: 23px;
        }}
        QTabBar::tab:selected {{
            color: {p['accent']};
            background: {p['hover']};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            color: {p['text']};
            background: {p['alternate_row']};
        }}

        /* Menus and dialogs. */
        QMenuBar {{
            background: {p['window_bg']};
            color: {p['text']};
            border-bottom: 1px solid {p['border']};
        }}
        QMenuBar::item {{
            padding: 6px 12px;
            background: transparent;
            border-radius: 7px;
        }}
        QMenuBar::item:selected {{ background: {p['hover']}; }}
        QMenu {{
            background: {p['panel_bg']};
            color: {p['text']};
            border: 1px solid {p['border']};
            padding: 5px;
        }}
        QMenu::item {{
            padding: 7px 25px 7px 21px;
            border-radius: 7px;
        }}
        QMenu::item:selected {{
            background: {p['hover']};
            color: {p['text']};
        }}
        QMenu::separator {{
            height: 1px;
            background: {p['border']};
            margin: 4px 8px;
        }}
        QMessageBox QLabel {{ color: {p['text']}; }}
        QDialogButtonBox QPushButton {{ min-width: 92px; }}

        /* Supporting controls. */
        QSplitter::handle {{
            background: transparent;
        }}
        QSplitter::handle:hover {{
            background: {p['hover']};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {p['border']};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p['border']};
            border-radius: 4px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {p['muted']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QLabel#photoFrame {{
            border: 1px solid {p['border']};
            border-radius: 10px;
            background: {p['alternate_row']};
            color: {p['muted']};
        }}
        QToolTip {{
            background: {p['panel_bg']};
            color: {p['text']};
            border: 1px solid {p['border']};
            padding: 5px 8px;
        }}
        QStatusBar {{
            background: {p['window_bg']};
            color: {p['text_secondary']};
        }}
    """


class ThemeManager:
    """Single point for theme persistence, QSS and semantic colours."""

    SETTINGS_KEY = "appearance/theme"
    LIGHT = "light"
    DARK = "dark"

    def __init__(self, settings: QSettings | None = None):
        self.settings = settings or QSettings("PersonnelTracker", "PersonnelTracker")
        self._theme = self.current_theme()

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

    def palette(self) -> dict[str, str]:
        return dict(DARK_PALETTE if self._theme == self.DARK else LIGHT_PALETTE)

    def color(self, role: str) -> QColor:
        return QColor(self.palette().get(role, self.palette()["text"]))
