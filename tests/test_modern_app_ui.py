from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from modern_app_ui import install_modern_app_ui
from planning_ui import install_planning_ui
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from theme import LIGHT_PALETTE
from ui import MainWindow
from workflow_ui import install_workflow_ui


class ModernAppUiTests(unittest.TestCase):
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
            install_modern_app_ui,
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_global_palette_uses_modern_tokens(self):
        self.assertEqual(LIGHT_PALETTE["window_bg"], "#f5f7fb")
        self.assertEqual(LIGHT_PALETTE["accent"], "#4169e1")
        self.assertEqual(LIGHT_PALETTE["border"], "#e3e8ef")

    def test_planning_uses_common_visual_language(self):
        self.assertEqual(self.window.planning_month_label.objectName(), "planningMonthLabel")
        self.assertTrue(self.window.planning_department.property("modernFilter"))
        self.assertGreaterEqual(self.window.planning_department.minimumHeight(), 34)

    def test_today_metrics_receive_subtle_elevation(self):
        metrics = [
            frame
            for frame in self.window.today_page.findChildren(QFrame)
            if frame.objectName() == "todayMetric"
        ]
        self.assertEqual(len(metrics), 5)
        self.assertTrue(all(frame.graphicsEffect() is not None for frame in metrics))
        self.assertIsNotNone(self.window.today_page.attention_panel.graphicsEffect())

    def test_common_actions_get_semantic_icons(self):
        delete = QPushButton("Удалить запись", self.window)
        self.window.polish_modern_button(delete)
        self.assertEqual(delete.property("role"), "danger")
        self.assertEqual(delete.property("modernIconKind"), "delete")
        self.assertFalse(delete.icon().isNull())

        save = QPushButton("Сохранить", self.window)
        self.window.polish_modern_button(save)
        self.assertEqual(save.property("modernIconKind"), "save")
        self.assertFalse(save.icon().isNull())

    def test_install_is_idempotent(self):
        filter_object = self.window.modern_app_button_filter
        install_modern_app_ui(self.window)
        self.assertIs(self.window.modern_app_button_filter, filter_object)


if __name__ == "__main__":
    unittest.main()
