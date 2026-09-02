from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


class ThemeManager:
    """Small, central theme layer ready for the visual update in v0.6."""

    SETTINGS_KEY = "appearance/theme"
    LIGHT = "light"
    DARK = "dark"

    _LIGHT_QSS = """
        QMainWindow, QDialog { background: #f7f8fa; color: #1f2937; }
        QLineEdit, QComboBox, QTextEdit, QDateEdit, QTableWidget, QTreeWidget {
            background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
        }
        QPushButton { background: #ffffff; border: 1px solid #94a3b8; border-radius: 5px; padding: 5px 9px; }
        QPushButton:hover { background: #eaf2ff; }
        QHeaderView::section { background: #e9eef5; padding: 5px; border: 0; border-bottom: 1px solid #cbd5e1; }
    """
    _DARK_QSS = """
        QMainWindow, QDialog { background: #20242b; color: #e5e7eb; }
        QLineEdit, QComboBox, QTextEdit, QDateEdit, QTableWidget, QTreeWidget {
            background: #2b313b; color: #e5e7eb; border: 1px solid #4b5563; border-radius: 5px;
        }
        QPushButton { background: #303844; color: #e5e7eb; border: 1px solid #64748b; border-radius: 5px; padding: 5px 9px; }
        QPushButton:hover { background: #3d4a5b; }
        QHeaderView::section { background: #303844; color: #e5e7eb; padding: 5px; border: 0; border-bottom: 1px solid #4b5563; }
    """

    def __init__(self, settings: QSettings | None = None):
        self.settings = settings or QSettings("PersonnelTracker", "PersonnelTracker")

    def current_theme(self) -> str:
        value = str(self.settings.value(self.SETTINGS_KEY, self.LIGHT))
        return value if value in {self.LIGHT, self.DARK} else self.LIGHT

    def apply(self, app: QApplication, theme: str | None = None) -> str:
        selected = theme or self.current_theme()
        selected = selected if selected in {self.LIGHT, self.DARK} else self.LIGHT
        app.setStyleSheet(self._DARK_QSS if selected == self.DARK else self._LIGHT_QSS)
        self.settings.setValue(self.SETTINGS_KEY, selected)
        return selected

    def toggle(self, app: QApplication) -> str:
        next_theme = self.DARK if self.current_theme() == self.LIGHT else self.LIGHT
        return self.apply(app, next_theme)
