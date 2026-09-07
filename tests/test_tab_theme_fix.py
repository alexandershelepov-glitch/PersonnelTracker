from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QTabWidget, QVBoxLayout, QWidget

from tab_theme_fix import install_tab_theme_fix


class FakeTheme:
    def palette(self):
        return {
            "window_bg": "#1c1f26",
            "border": "#3d434f",
            "text_secondary": "#9aa4b2",
            "text": "#e5e7eb",
            "accent": "#4a82f0",
            "hover": "#303845",
        }


class TabThemeFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tabs_use_application_theme_instead_of_document_mode(self):
        window = QWidget()
        window.theme_manager = FakeTheme()
        window._sync_theme_controls = lambda: None
        layout = QVBoxLayout(window)
        tabs = QTabWidget(window)
        tabs.setDocumentMode(True)
        tabs.addTab(QWidget(), "Справочник")
        tabs.addTab(QWidget(), "Сформировать команду")
        layout.addWidget(tabs)

        install_tab_theme_fix(window)

        self.assertFalse(tabs.documentMode())
        style = tabs.styleSheet()
        self.assertIn("#1c1f26", style)
        self.assertIn("#e5e7eb", style)
        self.assertIn("#4a82f0", style)


if __name__ == "__main__":
    unittest.main()
