from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from modern_directory_ui import install_modern_directory_ui
from modern_elevation_ui import install_modern_elevation_ui
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui
from workspace_resize_ui import install_workspace_resize_ui


class ModernElevationUiTests(unittest.TestCase):
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
            install_workspace_resize_ui,
            install_modern_directory_ui,
            install_modern_elevation_ui,
        ):
            install(self.window)
        self.window.nav_group.button(0).click()
        self.window.composition_tabs.setCurrentIndex(0)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_reference_surfaces_have_subtle_drop_shadows(self):
        self.assertIsInstance(
            self.window.modern_directory_toolbar.graphicsEffect(),
            QGraphicsDropShadowEffect,
        )
        self.assertIsInstance(
            self.window.composition_directory_table.graphicsEffect(),
            QGraphicsDropShadowEffect,
        )
        self.assertIsInstance(
            self.window.composition_empty_state.graphicsEffect(),
            QGraphicsDropShadowEffect,
        )

    def test_install_is_idempotent(self):
        effect = self.window.modern_directory_toolbar.graphicsEffect()
        install_modern_elevation_ui(self.window)
        self.assertIs(self.window.modern_directory_toolbar.graphicsEffect(), effect)


if __name__ == "__main__":
    unittest.main()
