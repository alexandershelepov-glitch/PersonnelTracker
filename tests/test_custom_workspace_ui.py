from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QHeaderView, QMenu

from acceptance_ui_polish import install_acceptance_ui_polish
from composition_ui import install_composition_ui
from custom_workspace_ui import install_custom_workspace_ui
from interface_polish import install_interface_polish
from ui import MainWindow
from workflow_ui import install_workflow_ui


class CustomWorkspaceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.window = self._open_window("personnel.db")

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _open_window(self, name: str) -> MainWindow:
        window = MainWindow(Path(self.tmp.name) / name)
        install_acceptance_ui_polish(window)
        install_custom_workspace_ui(window)
        window.show()
        self.app.processEvents()
        return window

    def _first_two_visible_columns(self, window: MainWindow) -> tuple[int, int]:
        table = window.staff_table
        visible = [
            column for column in range(table.columnCount())
            if not table.isColumnHidden(column)
        ]
        self.assertGreaterEqual(len(visible), 2)
        return visible[0], visible[1]

    def test_shds_columns_are_movable_and_resettable(self):
        table = self.window.staff_table
        header = self.window.shds_custom_header
        first, second = self._first_two_visible_columns(self.window)
        original_widths = tuple(self.window.shds_default_widths)
        original_hidden = tuple(self.window.shds_default_hidden)

        self.assertTrue(header.sectionsMovable())
        header.moveSection(header.visualIndex(first), header.visualIndex(second))
        table.setColumnWidth(second, table.columnWidth(second) + 37)
        self.app.processEvents()

        self.assertNotEqual(header.visualIndex(first), first)
        self.assertIsNotNone(self.window.settings.value("workspace/shds_header_state"))

        self.window.reset_shds_columns_action.trigger()
        self.app.processEvents()

        for logical in range(header.count()):
            self.assertEqual(header.visualIndex(logical), logical)
        self.assertEqual(
            tuple(table.columnWidth(column) for column in range(table.columnCount())),
            original_widths,
        )
        self.assertEqual(
            tuple(table.isColumnHidden(column) for column in range(table.columnCount())),
            original_hidden,
        )
        self.assertIsNone(self.window.settings.value("workspace/shds_header_state"))

    def test_shds_layout_survives_restart_and_reset_clears_it(self):
        table = self.window.staff_table
        header = self.window.shds_custom_header
        first, second = self._first_two_visible_columns(self.window)
        changed_width = table.columnWidth(second) + 41

        header.moveSection(header.visualIndex(first), header.visualIndex(second))
        table.setColumnWidth(second, changed_width)
        self.app.processEvents()
        changed_visual = header.visualIndex(first)
        self.assertIsNotNone(self.settings.value("workspace/shds_header_state"))

        second_window = self._open_window("personnel_second.db")
        try:
            self.assertEqual(second_window.shds_custom_header.visualIndex(first), changed_visual)
            self.assertEqual(second_window.staff_table.columnWidth(second), changed_width)
            second_window.reset_shds_columns_action.trigger()
            self.app.processEvents()
            self.assertIsNone(self.settings.value("workspace/shds_header_state"))
        finally:
            second_window.close()
            second_window.deleteLater()
            self.app.processEvents()

        third_window = self._open_window("personnel_third.db")
        try:
            for logical in range(third_window.shds_custom_header.count()):
                self.assertEqual(third_window.shds_custom_header.visualIndex(logical), logical)
            self.assertEqual(
                tuple(third_window.staff_table.isColumnHidden(column) for column in range(third_window.staff_table.columnCount())),
                tuple(third_window.shds_default_hidden),
            )
        finally:
            third_window.close()
            third_window.deleteLater()
            self.app.processEvents()

    def test_resize_and_reorder_do_not_write_legacy_sqlite_layout(self):
        table = self.window.staff_table
        header = self.window.shds_custom_header
        first, second = self._first_two_visible_columns(self.window)

        header.moveSection(header.visualIndex(first), header.visualIndex(second))
        table.setColumnWidth(second, table.columnWidth(second) + 33)
        self.app.processEvents()

        # QSettings is the only layout store; the legacy SQLite settings stay absent.
        self.assertIsNotNone(self.settings.value("workspace/shds_header_state"))
        self.assertIsNone(self.window.db.get_setting("shds_column_widths", None))
        self.assertIsNone(self.window.db.get_setting("shds_visible_columns", None))

    def test_column_menu_hides_persistently_without_sqlite(self):
        table = self.window.staff_table
        target = 3  # a user column ("Отделение"), never the hidden technical ID
        self.assertFalse(table.isColumnHidden(target))

        class _FakeSender:
            def mapToGlobal(self, _point):
                return QPoint(0, 0)

            def rect(self):
                return QRect(0, 0, 10, 10)

        # Exercise the real menu wiring without a blocking modal exec().
        created = {}

        class _FakeMenu:
            def __init__(self, parent=None):
                self.actions = []
                created["menu"] = self

            def addAction(self, text):
                action = QAction(text)
                self.actions.append(action)
                return action

            def exec(self, *_args, **_kwargs):
                return None

        original_sender = self.window.sender
        self.window.sender = lambda: _FakeSender()
        try:
            with patch("ui.QMenu", _FakeMenu):
                self.window.show_column_menu()
        finally:
            self.window.sender = original_sender

        menu = created["menu"]
        action = next(
            item for item in menu.actions
            if item.text() == self.window.staff_headers[target]
        )
        self.assertTrue(action.isChecked())
        action.setChecked(False)
        self.app.processEvents()

        self.assertTrue(table.isColumnHidden(target))
        self.assertIsNotNone(self.settings.value("workspace/shds_header_state"))
        self.assertIsNone(self.window.db.get_setting("shds_visible_columns", None))
        self.assertIsNone(self.window.db.get_setting("shds_column_widths", None))

        second_window = self._open_window("personnel_hidden.db")
        try:
            self.assertTrue(second_window.staff_table.isColumnHidden(target))
        finally:
            second_window.close()
            second_window.deleteLater()
            self.app.processEvents()

    def test_reset_restores_factory_layout_without_sqlite(self):
        table = self.window.staff_table
        header = self.window.shds_custom_header
        factory_widths = tuple(self.window.shds_default_widths)
        factory_hidden = tuple(self.window.shds_default_hidden)

        table.setColumnWidth(1, table.columnWidth(1) + 25)
        table.setColumnHidden(3, True)
        self.window.persist_shds_workspace()
        self.app.processEvents()
        self.assertIsNotNone(self.settings.value("workspace/shds_header_state"))

        self.window.reset_shds_columns_action.trigger()
        self.app.processEvents()

        for logical in range(header.count()):
            self.assertEqual(header.visualIndex(logical), logical)
        self.assertEqual(
            tuple(table.columnWidth(column) for column in range(table.columnCount())),
            factory_widths,
        )
        self.assertEqual(
            tuple(table.isColumnHidden(column) for column in range(table.columnCount())),
            factory_hidden,
        )
        self.assertIsNone(self.settings.value("workspace/shds_header_state"))
        self.assertIsNone(self.window.db.get_setting("shds_visible_columns", None))
        self.assertIsNone(self.window.db.get_setting("shds_column_widths", None))


class TodayTableWorkspaceUiTests(unittest.TestCase):
    ABSENT_KEY = "today/absent_header_state"
    SHIFT_KEY = "today/shift_header_state"

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.window = self._open_window("today.db")

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _open_window(self, name: str) -> MainWindow:
        window = MainWindow(Path(self.tmp.name) / name)
        install_workflow_ui(window)
        install_interface_polish(window)
        install_custom_workspace_ui(window)
        window.show()
        self.app.processEvents()
        return window

    def test_today_tables_are_resizable_gridded_and_refresh_safe(self):
        page = self.window.today_page
        grid_line = self.window.theme_manager.palette()["grid_line"]

        for table in (page.absent_table, page.shift_table):
            header = table.horizontalHeader()
            self.assertTrue(table.showGrid())
            self.assertTrue(header.sectionsMovable())
            self.assertFalse(header.stretchLastSection())
            for column in range(table.columnCount()):
                self.assertEqual(header.sectionResizeMode(column), QHeaderView.Interactive)
            # Grid colour is owned by the shared theme, not a local override.
            self.assertEqual(table.styleSheet(), "")
        self.window.theme_manager.apply(self.app, "light")
        self.assertIn(grid_line, self.app.styleSheet())

        table = page.absent_table
        header = table.horizontalHeader()
        changed_width = table.columnWidth(0) + 47
        header.moveSection(0, 1)
        table.setColumnWidth(0, changed_width)
        self.app.processEvents()
        changed_visual = header.visualIndex(0)
        self.assertIsNotNone(self.settings.value(self.ABSENT_KEY))

        # This used to reset the table back to Stretch/ResizeToContents through
        # interface_polish.py. The v1.1 layer must preserve the user's layout.
        page.refresh()
        self.app.processEvents()
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.Interactive)
        self.assertEqual(header.visualIndex(0), changed_visual)
        self.assertEqual(table.columnWidth(0), changed_width)

    def test_today_table_layout_persists_restart_and_reset(self):
        page = self.window.today_page
        absent_width = page.absent_table.columnWidth(1) + 39
        shift_width = page.shift_table.columnWidth(1) + 31
        page.absent_table.setColumnWidth(1, absent_width)
        page.shift_table.setColumnWidth(1, shift_width)
        page.absent_table.horizontalHeader().moveSection(0, 2)
        self.app.processEvents()

        self.assertIsNotNone(self.settings.value(self.ABSENT_KEY))
        self.assertIsNotNone(self.settings.value(self.SHIFT_KEY))
        changed_visual = page.absent_table.horizontalHeader().visualIndex(0)

        second = self._open_window("today_second.db")
        try:
            self.assertEqual(second.today_page.absent_table.columnWidth(1), absent_width)
            self.assertEqual(second.today_page.shift_table.columnWidth(1), shift_width)
            self.assertEqual(second.today_page.absent_table.horizontalHeader().visualIndex(0), changed_visual)

            second.reset_today_columns_action.trigger()
            self.app.processEvents()
            self.assertIsNone(self.settings.value(self.ABSENT_KEY))
            self.assertIsNone(self.settings.value(self.SHIFT_KEY))
            for table in (second.today_page.absent_table, second.today_page.shift_table):
                header = table.horizontalHeader()
                for logical in range(header.count()):
                    self.assertEqual(header.visualIndex(logical), logical)
                    self.assertEqual(header.sectionResizeMode(logical), QHeaderView.Interactive)
        finally:
            second.close()
            second.deleteLater()
            self.app.processEvents()


class CompositionTabOrderUiTests(unittest.TestCase):
    KEY = "workspace/composition_tab_order"
    OLD_PANEL_KEY = "workspace/directory_action_panel"

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings_patch = patch("ui.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.window = self._open_window("personnel.db")

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def _open_window(self, name: str) -> MainWindow:
        window = MainWindow(Path(self.tmp.name) / name)
        # Mirrors the application order: Today exists before Composition so the
        # "Сформировать команду" quick action can be exercised.
        install_workflow_ui(window)
        install_composition_ui(window)
        install_custom_workspace_ui(window)
        window.show()
        self.app.processEvents()
        return window

    def _view_menu_texts(self, window: MainWindow) -> list[str]:
        for action in window.menuBar().actions():
            menu = action.menu()
            if isinstance(menu, QMenu) and menu.title() == "Вид":
                texts: list[str] = []

                def collect(current) -> None:
                    for item in current.actions():
                        texts.append(item.text())
                        if item.menu() is not None:
                            collect(item.menu())

                collect(menu)
                return texts
        return []

    def test_factory_tabs_are_directly_movable_and_old_panel_ui_is_gone(self):
        w = self.window
        self.assertTrue(w.composition_tabs.isMovable())
        self.assertEqual(w.composition_tab_current_order(), ["directory", "team", "shds"])

        menu_texts = self._view_menu_texts(w)
        self.assertIn("Сбросить порядок вкладок Состава", menu_texts)
        self.assertNotIn("Настроить панель действий Справочника…", menu_texts)
        self.assertNotIn("Сбросить панель действий Справочника", menu_texts)
        self.assertIsNone(self.settings.value(self.OLD_PANEL_KEY))

    def test_user_tab_order_persists_restart_and_reset(self):
        w = self.window
        w.composition_tabs.tabBar().moveTab(2, 0)
        self.app.processEvents()

        self.assertEqual(w.composition_tab_current_order(), ["shds", "directory", "team"])
        saved = self.settings.value(self.KEY)
        self.assertEqual(json.loads(str(saved)), ["shds", "directory", "team"])

        second = self._open_window("personnel_second.db")
        try:
            self.assertEqual(second.composition_tab_current_order(), ["shds", "directory", "team"])
            second.reset_composition_tab_order_action.trigger()
            self.app.processEvents()
            self.assertEqual(second.composition_tab_current_order(), ["directory", "team", "shds"])
            self.assertIsNone(self.settings.value(self.KEY))
        finally:
            second.close()
            second.deleteLater()
            self.app.processEvents()

        third = self._open_window("personnel_third.db")
        try:
            self.assertEqual(third.composition_tab_current_order(), ["directory", "team", "shds"])
        finally:
            third.close()
            third.deleteLater()
            self.app.processEvents()

    def test_invalid_saved_order_falls_back_to_factory(self):
        broken_values = (
            "{broken",
            '["directory", "directory", "shds"]',
            '["directory", "team"]',
            '["directory", "team", "unknown"]',
        )
        for index, broken in enumerate(broken_values):
            self.settings.setValue(self.KEY, broken)
            window = self._open_window(f"broken_{index}.db")
            try:
                self.assertEqual(window.composition_tab_current_order(), ["directory", "team", "shds"])
                self.assertIsNone(self.settings.value(self.KEY))
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_navigation_targets_survive_tab_reorder(self):
        w = self.window
        tabs = w.composition_tabs
        tabs.tabBar().moveTab(2, 0)
        self.app.processEvents()
        self.assertEqual(w.composition_tab_current_order(), ["shds", "directory", "team"])

        tabs.setCurrentIndex(0)
        composition_button = w.nav_group.button(0)
        self.assertIsNotNone(composition_button)
        composition_button.click()
        self.app.processEvents()
        self.assertIs(tabs.currentWidget(), w.composition_directory)

        tabs.setCurrentIndex(0)
        self.assertTrue(hasattr(w, "today_page"))
        self.assertTrue(hasattr(w.today_page, "team"))
        w.today_page.team.click()
        self.app.processEvents()
        self.assertIs(tabs.currentWidget(), w.composition_team_tab)

    def test_superseded_panel_preference_is_cleaned(self):
        self.settings.setValue(self.OLD_PANEL_KEY, '{"order": ["open", "copy"], "hidden": ["copy"]}')
        other = self._open_window("cleanup.db")
        try:
            self.assertIsNone(self.settings.value(self.OLD_PANEL_KEY))
            self.assertEqual(other.composition_tab_current_order(), ["directory", "team", "shds"])
        finally:
            other.close()
            other.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
