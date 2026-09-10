from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

from assignment_history_compat import install_assignment_history_features
from assignment_history_report_ui import install_assignment_history_report_ui
from backup_local import install_backup_features
from csv_data import install_csv_features
from date_state_report_ui import install_date_state_report_ui
from release_polish_ui import install_release_polish_ui
from reports_ui import install_reports_ui
from service_page_scroll import install_service_page_scroll
from staffing_report_ui import install_staffing_report_ui
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui
from config import APP_VERSION


class ReleasePolishUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / "personnel.db")
        for install in (
            install_backup_features,
            install_csv_features,
            install_assignment_history_features,
            install_temporal_snapshot_features,
            install_reports_ui,
            install_staffing_report_ui,
            install_date_state_report_ui,
            install_assignment_history_report_ui,
            install_service_page_scroll,
            install_workflow_ui,
            install_release_polish_ui,
        ):
            install(self.window)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_visible_version_is_centralized(self):
        self.assertEqual(self.window.windowTitle(), f"PersonnelTracker — v{APP_VERSION}")
        sidebar_versions = [
            label.text()
            for label in self.window.findChildren(QLabel)
            if label.objectName() == "appSubtitle" and label.text().startswith("v")
        ]
        self.assertIn(f"v{APP_VERSION}", sidebar_versions)

    def test_existing_reports_description_has_no_old_development_wording(self):
        texts = [label.text() for label in self.window.findChildren(QLabel)]
        self.assertIn("Рабочие отчёты и выгрузки на основе данных приложения.", texts)
        self.assertFalse(any("Первый отчёт" in text for text in texts))

    def test_lazy_report_views_remove_old_version_labels(self):
        date_view = self.window.date_state_report_view_type()
        history_view = self.window.assignment_history_report_view_type()
        texts = [label.text() for label in date_view.findChildren(QLabel)]
        texts += [label.text() for label in history_view.findChildren(QLabel)]
        self.assertFalse(any("v0.8" in text for text in texts))
        date_view.deleteLater()
        history_view.deleteLater()


if __name__ == "__main__":
    unittest.main()
