from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QCalendarWidget, QHeaderView, QMessageBox

from acceptance_ui_polish import install_acceptance_ui_polish
from ui import MainWindow


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
        install_acceptance_ui_polish(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_position_and_fio_columns_are_user_resizable(self):
        header = self.window.staff_table.horizontalHeader()
        for name in ("Должность", "ФИО"):
            column = self.window.staff_headers.index(name)
            self.assertEqual(header.sectionResizeMode(column), QHeaderView.Interactive)

    def test_long_messagebox_actions_are_readable(self):
        box = QMessageBox(self.window)
        box.setText("Назначить нового работника на штатную единицу?")
        first = box.addButton("Выбрать существующую вакансию", QMessageBox.AcceptRole)
        second = box.addButton("Создать новую штатную единицу", QMessageBox.ActionRole)
        third = box.addButton("Пока оставить без штатной единицы", QMessageBox.RejectRole)
        box.show()
        self.app.processEvents()

        self.assertGreaterEqual(box.minimumWidth(), 760)
        self.assertGreaterEqual(first.minimumWidth(), 230)
        self.assertGreaterEqual(second.minimumWidth(), 230)
        self.assertGreaterEqual(third.minimumWidth(), 230)
        box.close()

    def test_calendar_popup_removes_global_table_cell_padding(self):
        calendar = QCalendarWidget(self.window)
        calendar.show()
        self.app.processEvents()

        stylesheet = calendar.styleSheet()
        self.assertIn("QTableView::item", stylesheet)
        self.assertIn("padding: 0px", stylesheet)
        calendar.close()


if __name__ == "__main__":
    unittest.main()
