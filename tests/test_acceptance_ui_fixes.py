from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QHeaderView

import ui
from ui import MainWindow


class _FakeButton:
    def __init__(self, text: str):
        self.text = text
        self.minimum_width = 0

    def setMinimumWidth(self, width: int) -> None:
        self.minimum_width = width


class _FakeMessageBox:
    AcceptRole = 1
    ActionRole = 2
    RejectRole = 3
    last_instance = None

    def __init__(self, parent=None):
        type(self).last_instance = self
        self.parent = parent
        self.minimum_width = 0
        self.buttons = []
        self._clicked = None

    def setWindowTitle(self, _title: str) -> None:
        pass

    def setText(self, _text: str) -> None:
        pass

    def addButton(self, text: str, role):
        button = _FakeButton(text)
        self.buttons.append((button, role))
        return button

    def setMinimumWidth(self, width: int) -> None:
        self.minimum_width = width

    def exec(self):
        return 0

    def clickedButton(self):
        return self._clicked


class _FakeEmployeeDialog:
    def __init__(self, service, employee_id=None, parent=None):
        self.created_in_dialog = True
        self.employee_id = 1

    def exec(self):
        return 1


class AcceptanceUiFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_position_and_fio_columns_are_user_resizable(self):
        header = self.window.staff_table.horizontalHeader()
        for name in ("Должность", "ФИО"):
            column = self.window.staff_headers.index(name)
            self.assertEqual(header.sectionResizeMode(column), QHeaderView.Interactive)
            self.assertGreater(self.window.staff_table.columnWidth(column), 100)

    def test_assignment_choice_dialog_keeps_long_buttons_readable(self):
        with patch.object(ui, "EmployeeDialog", _FakeEmployeeDialog), patch.object(ui, "QMessageBox", _FakeMessageBox):
            self.window.add_employee()

        choice = _FakeMessageBox.last_instance
        self.assertIsNotNone(choice)
        self.assertGreaterEqual(choice.minimum_width, 720)
        widths = {button.text: button.minimum_width for button, _role in choice.buttons}
        self.assertGreaterEqual(widths["Выбрать существующую вакансию"], 220)
        self.assertGreaterEqual(widths["Создать новую штатную единицу"], 220)
        self.assertGreaterEqual(widths["Пока оставить без штатной единицы"], 240)


if __name__ == "__main__":
    unittest.main()
