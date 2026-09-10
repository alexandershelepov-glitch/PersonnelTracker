from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from modern_planning_ui import install_modern_planning_ui
from planning_ui import install_planning_ui
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class ModernPlanningUiTests(unittest.TestCase):
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
            install_planning_ui,
            install_modern_planning_ui,
        ):
            install(self.window)
        self.window._select_page(2)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_planning_has_compact_control_surface(self):
        panel = self.window.modern_planning_controls
        self.assertEqual(panel.objectName(), "planningControlPanel")
        self.assertFalse(self.window.planning_tabs.tabBar().expanding())
        self.assertEqual(self.window.planning_reset_filters.text(), "Сбросить")

    def test_primary_action_has_no_duplicate_plus(self):
        page = self.window.pages.widget(2)
        add_event = next(
            button
            for button in page.findChildren(QPushButton)
            if "Добавить событие" in button.text()
        )
        self.assertEqual(add_event.text(), "Добавить событие")

    def test_empty_state_and_hint_are_compact(self):
        self.assertLessEqual(self.window.planning_graph_empty.maximumHeight(), 112)
        self.assertGreaterEqual(self.window.planning_graph_empty.minimumHeight(), 88)
        hint = self.window.modern_planning_hint
        self.assertIsNotNone(hint)
        self.assertLessEqual(hint.maximumHeight(), 48)

    def test_install_is_idempotent(self):
        panel = self.window.modern_planning_controls
        install_modern_planning_ui(self.window)
        self.assertIs(self.window.modern_planning_controls, panel)


if __name__ == "__main__":
    unittest.main()
