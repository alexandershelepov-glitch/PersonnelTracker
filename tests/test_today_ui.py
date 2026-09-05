from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QCalendarWidget

from assignment_history_compat import install_assignment_history_features
from backup_local import install_backup_features
from csv_data import install_csv_features
from service_page_scroll import install_service_page_scroll
from temporal_snapshot import install_temporal_snapshot_features
from theme import ThemeManager
from ui import MainWindow
from workflow_ui import install_workflow_ui


class TodayUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name) / 'settings.ini'), QSettings.IniFormat)
        self.settings_patch = patch('ui.QSettings', return_value=settings)
        self.settings_patch.start()
        self.window = MainWindow(Path(self.tmp.name) / 'personnel.db')
        self.window.service.create_demo_data()
        for install in (install_backup_features, install_csv_features,
                        install_assignment_history_features, install_temporal_snapshot_features,
                        install_service_page_scroll, install_workflow_ui):
            install(self.window)
        self.window.show()
        self.app.processEvents()
        self.page = self.window.today_page

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_navigation_and_landing(self):
        self.assertIs(self.window.pages.currentWidget(), self.page)
        visible = [b.text() for b in self.window.nav_buttons if not b.isHidden()]
        self.assertCountEqual(visible, ['Сегодня', 'Состав', 'Планирование', 'Настройки'])
        for index in (0, 1, 2, 3, 4, 5):
            self.window._select_page(index)
            self.assertEqual(self.window.pages.currentIndex(), index)
        install_workflow_ui(self.window)
        self.assertEqual(self.window.pages.count(), 6)

    def test_date_metrics_and_details(self):
        chosen = QDate(2026, 8, 24)
        self.page.set_date(chosen)
        metrics = self.window.service.staff_metrics('2026-08-24')['total']
        for key, label in self.page.values.items():
            self.assertEqual(label.text(), str(metrics[key]))
        self.page.next.click()
        self.assertEqual(self.page.selected_date, chosen.addDays(1))
        self.page.previous.click()
        self.assertEqual(self.page.selected_date, chosen)
        self.page.open_details()
        self.assertEqual(self.window.summary_date.date(), chosen)
        self.assertEqual(self.window.state_date.date(), chosen)
        self.page.reset.click()
        self.assertEqual(self.page.selected_date, QDate.currentDate())

    def test_event_reuses_editor_and_selected_date(self):
        selected = QDate.currentDate().addDays(3)
        self.page.set_date(selected)
        with patch('ui.EventDialog') as editor:
            self.page.open_event()
            editor.return_value.start.setDate.assert_called_once_with(selected)
            editor.return_value.end.setDate.assert_called_once_with(selected)
            editor.return_value.exec.assert_called_once()

    def test_calendar_selection(self):
        selected = QDate(2026, 9, 12)
        def choose():
            dialog = self.app.activeModalWidget()
            dialog.findChild(QCalendarWidget).setSelectedDate(selected)
            dialog.accept()
        QTimer.singleShot(30, choose)
        self.page.calendar.click()
        self.assertEqual(self.page.selected_date, selected)

    def test_theme_resize_and_data_unchanged(self):
        with self.window.db.connect() as conn:
            before = list(conn.iterdump())
        for theme in (ThemeManager.LIGHT, ThemeManager.DARK):
            self.window.theme_manager.apply(self.app, theme)
            self.window._sync_theme_controls()
            for width, height in ((760, 520), (1100, 760), (1500, 900)):
                self.window.resize(width, height)
                self.app.processEvents()
                self.assertLessEqual(self.page.widget().width(), self.page.viewport().width())
                self.assertIn(self.window.theme_manager.color('panel_bg').name(), self.page.styleSheet())
        with patch.object(QMessageBox, 'information') as notice:
            self.page.team.click()
            notice.assert_called_once()
        with self.window.db.connect() as conn:
            self.assertEqual(before, list(conn.iterdump()))
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
