from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate, QSettings, Qt
from PySide6.QtWidgets import QApplication

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from composition_ui import install_composition_ui
from csv_data import install_csv_features
from manual_team_ui import install_manual_team_ui
from navigation_context import install_context_navigation
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from ui import MainWindow
from workflow_ui import install_workflow_ui


class ManualTeamUiTests(unittest.TestCase):
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
            install_context_navigation,
        ):
            install(self.window)
        self.window.refresh_all()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _select_first_two(self):
        table = self.window.manual_team_table
        self.assertGreaterEqual(table.rowCount(), 2)
        table.item(0, 0).setCheckState(Qt.Checked)
        table.item(1, 0).setCheckState(Qt.Checked)
        self.app.processEvents()

    def test_manual_mode_lists_candidates_and_filters(self):
        self.assertEqual(
            [self.window.manual_team_mode_tabs.tabText(i) for i in range(2)],
            ["Ручной режим", "Полуавтоматический режим"],
        )
        self.assertEqual(self.window.manual_team_table.rowCount(), 4)
        self.window.manual_team_section.setCurrentText("1 отделение")
        self.app.processEvents()
        self.assertEqual(self.window.manual_team_table.rowCount(), 2)

    def test_manual_selection_and_copy(self):
        self._select_first_two()
        ids = self.window.manual_team_selected_ids()
        self.assertEqual(len(ids), 2)
        self.window.manual_team_copy_mode.setCurrentText("ФИО + табельный №")
        self.window.copy_manual_team()
        copied = QApplication.clipboard().text()
        self.assertIn("таб. №", copied)
        self.assertEqual(len([line for line in copied.splitlines() if line.strip()]), 2)

    def test_create_event_reuses_existing_batch_dialog_and_selected_date(self):
        self._select_first_two()
        chosen = QDate(2026, 9, 10)
        self.window.manual_team_date.setDate(chosen)
        ids = self.window.manual_team_selected_ids()
        with patch("ui.BatchEventDialog") as editor:
            dialog = editor.return_value
            dialog.exec.return_value = 0
            self.window.create_manual_team_event()
            editor.assert_called_once_with(self.window.service, self.window, preselected=ids)
            dialog.start.setDate.assert_called_once_with(chosen)
            dialog.end.setDate.assert_called_once_with(chosen)

    def test_today_action_carries_date_and_keeps_back_context(self):
        chosen = QDate(2026, 9, 12)
        self.window.today_page.set_date(chosen)
        self.window._select_page(
            self.window.pages.indexOf(self.window.today_page), record_history=False
        )
        self.window.today_page.team.click()
        self.app.processEvents()
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.assertEqual(self.window.composition_tabs.currentIndex(), 1)
        self.assertEqual(self.window.manual_team_mode_tabs.currentIndex(), 0)
        self.assertEqual(self.window.manual_team_date.date(), chosen)
        self.assertTrue(self.window._context_back_buttons[0].isVisible())

    def test_future_date_is_allowed(self):
        self.window.manual_team_date.setDate(QDate.currentDate().addMonths(2))
        self.app.processEvents()
        self.assertGreater(self.window.manual_team_table.rowCount(), 0)


if __name__ == "__main__":
    unittest.main()
