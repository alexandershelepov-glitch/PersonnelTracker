from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QAbstractItemView

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from employee_profile_ui import install_employee_profile_ui
from planning_ui import install_planning_ui
from planning_usability import install_planning_usability
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class PlanningUsabilityTests(unittest.TestCase):
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
            install_planning_ui,
            install_planning_usability,
        ):
            install(self.window)
        self.window.refresh_all()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_split_tables_have_identical_row_geometry(self):
        people = self.window.planning_people_table
        days = self.window.planning_days_table
        self.assertEqual(people.rowCount(), days.rowCount())
        self.assertEqual(people.horizontalHeader().height(), days.horizontalHeader().height())
        self.assertEqual(people.verticalScrollMode(), QAbstractItemView.ScrollPerPixel)
        self.assertEqual(days.verticalScrollMode(), QAbstractItemView.ScrollPerPixel)
        for row in range(people.rowCount()):
            self.assertEqual(people.rowHeight(row), days.rowHeight(row))

    def test_clicking_fio_opens_existing_event_editor_with_employee(self):
        people = self.window.planning_people_table
        employee_id = int(people.item(0, 0).data(0x0100))
        with patch("ui.EventDialog") as editor:
            dialog = editor.return_value
            dialog.exec.return_value = 0
            people.cellClicked.emit(0, 0)
            self.app.processEvents()
            editor.assert_called_once_with(
                self.window.service,
                parent=self.window,
                employee_id=employee_id,
            )
            dialog.start.setDate.assert_called_once()
            dialog.end.setDate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
