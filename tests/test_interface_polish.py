from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDateEdit, QLabel, QTableWidget

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from employee_profile_ui import install_employee_profile_ui
from interface_polish import install_interface_polish
from manual_team_ui import install_manual_team_ui
from navigation_context import install_context_navigation
from planning_ui import install_planning_ui
from planning_usability import install_planning_usability
from semi_auto_team_ui import install_semi_auto_team_ui
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class InterfacePolishTests(unittest.TestCase):
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
            install_manual_team_ui,
            install_semi_auto_team_ui,
            install_employee_profile_ui,
            install_planning_ui,
            install_planning_usability,
            install_context_navigation,
            install_interface_polish,
        ):
            install(self.window)
        self.window.refresh_all()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_visible_navigation_is_four_user_workflows(self):
        visible = [button.text() for button in self.window.nav_group.buttons() if not button.isHidden()]
        self.assertEqual(set(visible), {"Сегодня", "Состав", "Планирование", "Настройки"})

    def test_working_labels_do_not_expose_old_version_terms(self):
        texts = [label.text() for label in self.window.findChildren(QLabel) if label.isVisible()]
        self.assertFalse(any("v0.8.2" in text for text in texts))
        self.assertTrue(any("Состояние учитывает ШДС" in text for text in texts))

    def test_dates_and_tables_have_consistent_density(self):
        for editor in self.window.findChildren(QDateEdit):
            self.assertEqual(editor.displayFormat(), "dd.MM.yyyy")
        self.assertEqual(self.window.manual_team_table.verticalHeader().defaultSectionSize(), 30)
        self.assertEqual(self.window.semi_auto_team_table.verticalHeader().defaultSectionSize(), 30)
        self.assertEqual(self.window.planning_people_table.verticalHeader().defaultSectionSize(), 32)
        self.assertEqual(self.window.planning_days_table.verticalHeader().defaultSectionSize(), 32)

    def test_profile_uses_user_facing_history_copy(self):
        person = self.window.service.list_employees()[0]
        dialog = self.window.employee_profile_dialog_class(
            self.window.service, int(person["id"]), self.window
        )
        try:
            labels = [label.text() for label in dialog.findChildren(QLabel)]
            self.assertTrue(any("с момента начала её ведения в приложении" in text for text in labels))
            self.assertFalse(any("включения учёта v0.8" in text for text in labels))
            for table in dialog.findChildren(QTableWidget):
                self.assertEqual(table.verticalHeader().defaultSectionSize(), 30)
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
