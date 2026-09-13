from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLabel, QListWidget

from acceptance_ui_polish import install_acceptance_ui_polish
from composition_ui import install_composition_ui
from custom_workspace_ui import install_custom_workspace_ui
from modern_directory_ui import install_modern_directory_ui
from ui import MainWindow


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


class DirectoryActionPanelUiTests(unittest.TestCase):
    KEY = "workspace/directory_action_panel"

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
        install_composition_ui(window)
        install_modern_directory_ui(window)
        install_custom_workspace_ui(window)
        window.show()
        self.app.processEvents()
        return window

    def _is_shown(self, window: MainWindow, widget) -> bool:
        # Explicit visibility within the actions frame, independent of whether
        # the directory page is the current stacked page.
        return widget.isVisibleTo(window.directory_actions_frame)

    def test_factory_panel_layout(self):
        w = self.window
        layout = w.directory_actions_layout
        self.assertEqual(w.directory_copy_mode.objectName(), "directoryCopyMode")
        self.assertEqual(w.directory_copy_button.objectName(), "directoryCopyButton")
        self.assertEqual(w.directory_open_button.objectName(), "directoryOpenButton")
        # Counter pinned left, stretch between it and the configurable actions.
        self.assertEqual(layout.indexOf(w.directory_selection_label), 0)
        self.assertIsNotNone(layout.itemAt(1).spacerItem())
        self.assertEqual(layout.indexOf(w.directory_copy_mode), 2)
        self.assertEqual(layout.indexOf(w.directory_copy_button), 3)
        self.assertEqual(layout.indexOf(w.directory_open_button), 4)
        self.assertTrue(self._is_shown(w, w.directory_copy_mode))
        self.assertTrue(self._is_shown(w, w.directory_copy_button))
        self.assertTrue(self._is_shown(w, w.directory_open_button))
        self.assertIsNone(self.settings.value(self.KEY))

    def test_reorder_open_before_copy_keeps_copy_pair_adjacent(self):
        w = self.window
        w.directory_action_panel_apply(["open", "copy"], [])
        self.app.processEvents()
        layout = w.directory_actions_layout
        self.assertLess(layout.indexOf(w.directory_open_button), layout.indexOf(w.directory_copy_mode))
        self.assertEqual(layout.indexOf(w.directory_copy_button), layout.indexOf(w.directory_copy_mode) + 1)
        self.assertEqual(layout.indexOf(w.directory_selection_label), 0)
        self.assertTrue(self._is_shown(w, w.directory_open_button))
        self.assertTrue(self._is_shown(w, w.directory_copy_mode))
        self.assertTrue(self._is_shown(w, w.directory_copy_button))

    def test_hide_copy_hides_combo_and_button_together(self):
        w = self.window
        w.directory_action_panel_apply(["copy", "open"], ["copy"])
        self.assertFalse(self._is_shown(w, w.directory_copy_mode))
        self.assertFalse(self._is_shown(w, w.directory_copy_button))
        self.assertTrue(self._is_shown(w, w.directory_open_button))

    def test_hide_open_keeps_copy_group_visible(self):
        w = self.window
        w.directory_action_panel_apply(["copy", "open"], ["open"])
        self.assertFalse(self._is_shown(w, w.directory_open_button))
        self.assertTrue(self._is_shown(w, w.directory_copy_mode))
        self.assertTrue(self._is_shown(w, w.directory_copy_button))

    def test_hide_all_keeps_counter_visible_and_layout_intact(self):
        w = self.window
        w.directory_action_panel_apply(["copy", "open"], ["copy", "open"])
        self.assertFalse(self._is_shown(w, w.directory_open_button))
        self.assertFalse(self._is_shown(w, w.directory_copy_mode))
        self.assertFalse(self._is_shown(w, w.directory_copy_button))
        self.assertTrue(self._is_shown(w, w.directory_selection_label))
        self.assertEqual(w.directory_actions_layout.count(), 5)

    def test_saved_layout_survives_restart(self):
        w = self.window
        w.directory_action_panel_apply(["open", "copy"], ["copy"])
        w.directory_action_panel_save(["open", "copy"], ["copy"])
        self.app.processEvents()
        self.assertIsNotNone(self.settings.value(self.KEY))

        second = self._open_window("personnel_second.db")
        try:
            self.assertEqual(second.directory_action_panel_current_state(), (["open", "copy"], ["copy"]))
            layout = second.directory_actions_layout
            self.assertLess(layout.indexOf(second.directory_open_button), layout.indexOf(second.directory_copy_mode))
            self.assertFalse(self._is_shown(second, second.directory_copy_mode))
            self.assertFalse(self._is_shown(second, second.directory_copy_button))
            self.assertTrue(self._is_shown(second, second.directory_open_button))
        finally:
            second.close()
            second.deleteLater()
            self.app.processEvents()

    def test_reset_action_returns_factory_and_clears_key(self):
        w = self.window
        w.directory_action_panel_apply(["open", "copy"], ["copy"])
        w.directory_action_panel_save(["open", "copy"], ["copy"])
        w.reset_directory_action_panel_action.trigger()
        self.app.processEvents()

        self.assertEqual(w.directory_action_panel_current_state(), (["copy", "open"], []))
        layout = w.directory_actions_layout
        self.assertEqual(layout.indexOf(w.directory_copy_mode), 2)
        self.assertEqual(layout.indexOf(w.directory_copy_button), 3)
        self.assertEqual(layout.indexOf(w.directory_open_button), 4)
        self.assertTrue(self._is_shown(w, w.directory_open_button))
        self.assertTrue(self._is_shown(w, w.directory_copy_mode))
        self.assertIsNone(self.settings.value(self.KEY))

        third = self._open_window("personnel_third.db")
        try:
            self.assertEqual(third.directory_action_panel_current_state(), (["copy", "open"], []))
            self.assertTrue(self._is_shown(third, third.directory_open_button))
            self.assertTrue(self._is_shown(third, third.directory_copy_mode))
        finally:
            third.close()
            third.deleteLater()
            self.app.processEvents()

    def test_invalid_settings_fall_back_to_factory(self):
        broken_values = (
            "{broken",
            '{"order": ["copy", "hack"], "hidden": []}',
            '{"order": ["copy", "copy"], "hidden": []}',
            '{"order": ["copy"], "hidden": []}',
            '{"order": ["copy", "open"], "hidden": ["copy", "copy"]}',
            '{"order": ["copy", "open"], "hidden": ["hack"]}',
            "[]",
        )
        for index, broken in enumerate(broken_values):
            self.settings.setValue(self.KEY, broken)
            window = self._open_window(f"broken_{index}.db")
            try:
                self.assertEqual(window.directory_action_panel_current_state(), (["copy", "open"], []))
                self.assertTrue(self._is_shown(window, window.directory_open_button))
                self.assertTrue(self._is_shown(window, window.directory_copy_mode))
                self.assertTrue(self._is_shown(window, window.directory_copy_button))
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_reorder_and_hide_reuse_existing_widgets(self):
        w = self.window
        copy_mode = w.directory_copy_mode
        copy_button = w.directory_copy_button
        open_button = w.directory_open_button
        copy_callback = w.copy_composition_selection

        w.directory_action_panel_apply(["open", "copy"], ["open"])
        w.directory_action_panel_apply(["copy", "open"], [])

        self.assertIs(w.directory_copy_mode, copy_mode)
        self.assertIs(w.directory_copy_button, copy_button)
        self.assertIs(w.directory_open_button, open_button)
        self.assertIs(w.copy_composition_selection, copy_callback)
        layout = w.directory_actions_layout
        self.assertEqual(layout.indexOf(copy_button), layout.indexOf(copy_mode) + 1)

    def test_dialog_cancel_and_defaults_do_not_change_screen(self):
        w = self.window
        dialog = w.directory_action_panel_dialog_type(w)
        try:
            ids = [dialog.list.item(row).data(Qt.UserRole) for row in range(dialog.list.count())]
            self.assertEqual(ids, ["copy", "open"])
            self.assertTrue(all(dialog.list.item(row).checkState() == Qt.Checked for row in range(2)))

            moved = dialog.list.takeItem(0)
            dialog.list.insertItem(1, moved)
            dialog.list.item(1).setCheckState(Qt.Unchecked)
            self.assertEqual(dialog.state(), (["open", "copy"], ["copy"]))

            dialog.reject()
            self.assertEqual(w.directory_action_panel_current_state(), (["copy", "open"], []))
            self.assertIsNone(self.settings.value(self.KEY))
            self.assertEqual(w.directory_actions_layout.indexOf(w.directory_open_button), 4)
        finally:
            dialog.deleteLater()
            self.app.processEvents()

        dialog2 = w.directory_action_panel_dialog_type(w)
        try:
            moved = dialog2.list.takeItem(0)
            dialog2.list.insertItem(1, moved)
            dialog2.list.item(1).setCheckState(Qt.Unchecked)
            dialog2.restore_defaults()
            self.assertEqual(dialog2.state(), (["copy", "open"], []))

            dialog2.list.item(0).setCheckState(Qt.Unchecked)
            dialog2.save()
            self.assertEqual(w.directory_action_panel_current_state(), (["copy", "open"], ["copy"]))
            self.assertIsNotNone(self.settings.value(self.KEY))
            self.assertFalse(self._is_shown(w, w.directory_copy_mode))
            self.assertFalse(self._is_shown(w, w.directory_copy_button))
            self.assertTrue(self._is_shown(w, w.directory_open_button))
        finally:
            dialog2.deleteLater()
            self.app.processEvents()

    def test_dialog_is_compact_readable_and_keeps_controls(self):
        w = self.window
        dialog = w.directory_action_panel_dialog_type(w)
        try:
            # Short drag/visibility hint styled with the app secondary text role.
            hints = [
                label
                for label in dialog.findChildren(QLabel)
                if label.objectName() == "secondaryText" and label.wordWrap()
            ]
            self.assertEqual(len(hints), 1)
            self.assertIn("Перетащите пункты", hints[0].text())
            self.assertIn("Снимите флажок", hints[0].text())

            lists = dialog.findChildren(QListWidget)
            self.assertEqual(len(lists), 1)
            self.assertIs(dialog.list, lists[0])
            self.assertEqual(dialog.list.count(), 2)
            self.assertEqual(dialog.list.dragDropMode(), QAbstractItemView.InternalMove)
            for row in range(2):
                item = dialog.list.item(row)
                self.assertTrue(item.flags() & Qt.ItemIsUserCheckable)
                self.assertIn(item.checkState(), (Qt.Checked, Qt.Unchecked))

            # Compact, not fixed: bounded initial size with sane minimums.
            self.assertLessEqual(dialog.width(), 520)
            self.assertLessEqual(dialog.height(), 320)
            self.assertGreaterEqual(dialog.minimumWidth(), 300)
            self.assertGreaterEqual(dialog.minimumHeight(), 160)
            self.assertGreaterEqual(dialog.height(), dialog.minimumHeight())
            self.assertGreaterEqual(dialog.width(), dialog.minimumWidth())

            # Local stylesheet uses the live palette, no hard-coded light/dark.
            sheet = dialog.styleSheet()
            palette = w.theme_manager.palette()
            for role in ("panel_bg", "text", "text_secondary", "border", "hover", "selected", "selected_text"):
                self.assertIn(palette[role], sheet)
            for selector in (
                "QListWidget",
                "QListWidget::item",
                "QListWidget::item:hover",
                "QListWidget::item:selected",
            ):
                self.assertIn(selector, sheet)
        finally:
            dialog.deleteLater()
            self.app.processEvents()

    def test_dialog_styles_follow_current_theme(self):
        w = self.window
        manager = w.theme_manager
        try:
            manager.apply(self.app, "light")
            light_dialog = w.directory_action_panel_dialog_type(w)
            light_sheet = light_dialog.styleSheet()
            self.assertIn(manager.palette()["panel_bg"], light_sheet)
            light_dialog.deleteLater()

            manager.apply(self.app, "dark")
            dark_dialog = w.directory_action_panel_dialog_type(w)
            dark_sheet = dark_dialog.styleSheet()
            self.assertIn(manager.palette()["panel_bg"], dark_sheet)
            self.assertIn(manager.palette()["selected_text"], dark_sheet)
            self.assertNotEqual(light_sheet, dark_sheet)
            dark_dialog.deleteLater()
        finally:
            manager.apply(self.app, "light")
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
