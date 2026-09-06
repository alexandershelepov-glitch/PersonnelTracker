from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from employee_profile_ui import install_employee_profile_ui
from navigation_context import install_context_navigation
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class EmployeeProfileUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        self.window.service.create_demo_data()
        for install in (
            install_backup_features,
            install_csv_features,
            install_assignment_history_features,
            install_temporal_snapshot_features,
            install_service_page_scroll,
            install_workflow_ui,
            install_composition_ui,
            install_employee_profile_ui,
            install_context_navigation,
        ):
            install(self.window)
        self.window.refresh_all()
        self.employee_id = int(self.window.service.list_employees()[0]["id"])

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _dialog(self):
        import ui
        return ui.EmployeeDialog(self.window.service, self.employee_id, self.window)

    def test_profile_has_workflow_tabs_and_back_action(self):
        dialog = self._dialog()
        self.assertEqual(dialog.windowTitle(), "Профиль работника")
        self.assertEqual(
            [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())],
            ["Данные", "События", "Проверки и обучение", "Вооружение", "Назначения", "История"],
        )
        self.assertEqual(
            [dialog.profile_checks_tabs.tabText(index) for index in range(dialog.profile_checks_tabs.count())],
            ["Медкомиссия", "Периодическая проверка", "Обучение"],
        )
        self.assertTrue(any(button.text() == "← Назад" for button in dialog.findChildren(QPushButton)))
        dialog.close()

    def test_existing_record_tables_are_reused(self):
        dialog = self._dialog()
        self.assertTrue(dialog.tabs.widget(1).isAncestorOf(dialog.record_tables["Отсутствия"]))
        self.assertTrue(dialog.tabs.widget(3).isAncestorOf(dialog.record_tables["Оружие"]))
        self.assertTrue(dialog.profile_checks_page.isAncestorOf(dialog.record_tables["Медкомиссия"]))
        weapon_headers = [dialog.record_tables["Оружие"].horizontalHeaderItem(i).text()
                          for i in range(dialog.record_tables["Оружие"].columnCount())]
        self.assertEqual(weapon_headers, ["ID", "Наименование оружия", "Номер"])
        dialog.close()

    def test_assignment_history_and_chronology_are_visible(self):
        self.window.service.add_weapon(self.employee_id, "ПМ", "12345")
        self.window.service.add_medical_check(self.employee_id, "2026-09-01", "годен")
        dialog = self._dialog()
        dialog.refresh_records()
        self.assertGreaterEqual(dialog.profile_assignment_table.rowCount(), 1)
        history_sections = {
            dialog.profile_history_table.item(row, 1).text()
            for row in range(dialog.profile_history_table.rowCount())
        }
        self.assertIn("Назначения", history_sections)
        self.assertIn("Вооружение", history_sections)
        self.assertIn("Проверки", history_sections)
        dialog.close()

    def test_profile_save_still_uses_existing_employee_persistence(self):
        dialog = self._dialog()
        dialog.phone.setText("89991234567")
        with patch.object(QMessageBox, "information"):
            self.assertTrue(dialog.save())
        saved = self.window.service.get_employee(self.employee_id)
        self.assertEqual(saved["phone"], "89991234567")
        self.assertIn("89991234567", dialog.profile_phone.text())
        dialog.close()

    def test_control_shortcut_opens_grouped_checks(self):
        dialog = self._dialog()
        dialog.open_record_tab("Периодическая проверка")
        self.assertIs(dialog.tabs.currentWidget(), dialog.profile_checks_page)
        self.assertEqual(dialog.profile_checks_tabs.currentWidget(), dialog._profile_record_tabs["Периодическая проверка"])
        dialog.close()


if __name__ == "__main__":
    unittest.main()
