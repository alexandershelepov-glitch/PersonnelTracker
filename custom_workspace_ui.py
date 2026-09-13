"""v1.1 user-customizable workspace preferences.

Presentation only. Preferences are stored in QSettings and never modify
personnel data, assignment history or database schema.
"""
from __future__ import annotations

from typing import Any


def _install_directory_action_panel(window: Any) -> None:
    """Pilot v1.1 preference for the Directory action panel.

    Only the existing widgets are rearranged inside the existing QHBoxLayout:
    no button is recreated and no signal is reconnected.  The selection counter
    stays pinned on the left; only the user-configurable actions are ordered
    and hidden.  ``copy`` is one logical element: the mode combo and the
    "Копировать" button always move and hide together.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMenu,
        QPushButton,
        QVBoxLayout,
    )

    panel_copy_mode = getattr(window, "directory_copy_mode", None)
    panel_copy_button = getattr(window, "directory_copy_button", None)
    panel_open_button = getattr(window, "directory_open_button", None)
    panel_layout = getattr(window, "directory_actions_layout", None)
    panel_selection_label = getattr(window, "directory_selection_label", None)

    if (
        panel_copy_mode is None
        or panel_copy_button is None
        or panel_open_button is None
        or panel_layout is None
        or panel_selection_label is None
    ):
        # The modern Directory action panel is not installed in this host.
        return

    settings_key = "workspace/directory_action_panel"
    default_order = ("copy", "open")
    element_labels = {"copy": "Копирование", "open": "Открыть карточку"}
    element_widgets = {
        "copy": (panel_copy_mode, panel_copy_button),
        "open": (panel_open_button,),
    }

    def factory_state() -> tuple[list[str], list[str]]:
        return list(default_order), []

    def parse_state(raw: Any):
        """Return validated (order, hidden) or None when the value is unusable."""
        if isinstance(raw, dict):
            data = raw
        else:
            text = "" if raw is None else str(raw).strip()
            if not text:
                return None
            try:
                data = json.loads(text)
            except (TypeError, ValueError):
                return None
        if not isinstance(data, dict):
            return None
        order = data.get("order")
        hidden = data.get("hidden", [])
        if not isinstance(order, list) or not isinstance(hidden, list):
            return None
        # Exactly the known ids, once each, and only known hidden ids.
        if len(order) != len(default_order) or set(order) != set(default_order):
            return None
        if len(hidden) != len(set(hidden)) or any(entry not in element_labels for entry in hidden):
            return None
        return [str(entry) for entry in order], [str(entry) for entry in hidden]

    def current_state() -> tuple[list[str], list[str]]:
        raw = window.settings.value(settings_key)
        parsed = parse_state(raw) if raw is not None else None
        return parsed if parsed is not None else factory_state()

    def apply_state(order, hidden) -> None:
        # Detach only the configurable actions; the counter label and the
        # stretch item between it and the actions stay in place.
        for element_id in default_order:
            for widget in element_widgets[element_id]:
                panel_layout.removeWidget(widget)
        position = panel_layout.count()
        for element_id in order:
            visible = element_id not in hidden
            for widget in element_widgets[element_id]:
                widget.setVisible(visible)
                panel_layout.insertWidget(position, widget)
                position += 1

    def save_state(order, hidden) -> None:
        window.settings.setValue(
            settings_key,
            json.dumps({"order": list(order), "hidden": list(hidden)}, ensure_ascii=False),
        )

    def reset_panel() -> None:
        order, hidden = factory_state()
        apply_state(order, hidden)
        window.settings.remove(settings_key)

    # Apply the saved (or factory) layout at startup.
    apply_state(*current_state())

    class DirectoryActionPanelDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Настройка панели действий Справочника")
            # Compact pilot dialog: two rows plus a short hint.  A reasonable
            # initial/minimum size keeps it usable without a fixed geometry.
            self.resize(420, 220)
            self.setMinimumSize(360, 200)

            palette = window.theme_manager.palette()
            self.setStyleSheet(
                f"""
                QLabel#secondaryText {{
                    color: {palette['text_secondary']};
                }}
                QListWidget {{
                    background: {palette['panel_bg']};
                    color: {palette['text']};
                    border: 1px solid {palette['border']};
                    border-radius: 8px;
                    padding: 4px;
                    outline: none;
                }}
                QListWidget::item {{
                    color: {palette['text']};
                    padding: 7px 6px;
                    border-radius: 6px;
                }}
                QListWidget::item:hover {{
                    background: {palette['hover']};
                    color: {palette['text']};
                }}
                QListWidget::item:selected {{
                    background: {palette['selected']};
                    color: {palette['selected_text']};
                }}
                """
            )

            root = QVBoxLayout(self)
            hint = QLabel(
                "Перетащите пункты, чтобы изменить порядок. "
                "Снимите флажок, чтобы скрыть действие."
            )
            hint.setObjectName("secondaryText")
            hint.setWordWrap(True)
            root.addWidget(hint)

            self.list = QListWidget()
            self.list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.list.setDragDropMode(QAbstractItemView.InternalMove)
            self.list.setDefaultDropAction(Qt.MoveAction)
            self.list.setMinimumHeight(72)
            root.addWidget(self.list, 1)
            self.populate(*current_state())

            buttons = QHBoxLayout()
            defaults_button = QPushButton("По умолчанию")
            cancel_button = QPushButton("Отмена")
            save_button = QPushButton("Сохранить")
            save_button.setProperty("role", "primary")
            defaults_button.clicked.connect(self.restore_defaults)
            cancel_button.clicked.connect(self.reject)
            save_button.clicked.connect(self.save)
            buttons.addWidget(defaults_button)
            buttons.addStretch()
            buttons.addWidget(cancel_button)
            buttons.addWidget(save_button)
            root.addLayout(buttons)

        def populate(self, order, hidden) -> None:
            self.list.clear()
            for element_id in order:
                item = QListWidgetItem(element_labels[element_id])
                item.setData(Qt.UserRole, element_id)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked if element_id in hidden else Qt.Checked)
                self.list.addItem(item)

        def restore_defaults(self) -> None:
            self.populate(*factory_state())

        def state(self) -> tuple[list[str], list[str]]:
            order: list[str] = []
            hidden: list[str] = []
            for row in range(self.list.count()):
                item = self.list.item(row)
                element_id = item.data(Qt.UserRole)
                order.append(element_id)
                if item.checkState() != Qt.Checked:
                    hidden.append(element_id)
            return order, hidden

        def save(self) -> None:
            order, hidden = self.state()
            apply_state(order, hidden)
            save_state(order, hidden)
            self.accept()

    def open_panel_dialog() -> None:
        DirectoryActionPanelDialog(window).exec()

    view_menu = None
    for menu_action in window.menuBar().actions():
        menu = menu_action.menu()
        if isinstance(menu, QMenu) and menu.title() == "Вид":
            view_menu = menu
            break
    if view_menu is None:
        view_menu = window.menuBar().addMenu("Вид")

    configure_action = QAction("Настроить панель действий Справочника…", window)
    configure_action.triggered.connect(open_panel_dialog)
    view_menu.addAction(configure_action)

    reset_action = QAction("Сбросить панель действий Справочника", window)
    reset_action.triggered.connect(reset_panel)
    view_menu.addAction(reset_action)

    window.directory_action_panel_widgets = element_widgets
    window.directory_action_panel_default_order = tuple(default_order)
    window.directory_action_panel_apply = apply_state
    window.directory_action_panel_save = save_state
    window.directory_action_panel_current_state = current_state
    window.directory_action_panel_parse_state = parse_state
    window.directory_action_panel_dialog_type = DirectoryActionPanelDialog
    window.open_directory_action_panel = open_panel_dialog
    window.reset_directory_action_panel = reset_panel
    window.reset_directory_action_panel_action = reset_action


def install_custom_workspace_ui(window: Any) -> None:
    """Enable persistent SHDS column order without replacing legacy widths."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu

    if getattr(window, "_custom_workspace_ui_installed", False):
        return

    table = getattr(window, "staff_table", None)
    if table is None:
        # SHDS may be absent in some hosts; the Directory action panel is an
        # independent v1.1 preference and must still be installed.
        _install_directory_action_panel(window)
        window._custom_workspace_ui_installed = True
        return

    shds_header = table.horizontalHeader()
    shds_header.setSectionsMovable(True)

    settings_key = "workspace/shds_header_state"
    default_widths = tuple(table.columnWidth(column) for column in range(table.columnCount()))
    default_hidden = tuple(table.isColumnHidden(column) for column in range(table.columnCount()))

    def apply_shds_defaults() -> None:
        previous_block = shds_header.blockSignals(True)
        try:
            # moveSection() works with visual indexes. Resolve the current visual
            # index on every iteration so reset remains deterministic after any
            # user order.
            for logical in range(shds_header.count()):
                visual = shds_header.visualIndex(logical)
                if visual >= 0 and visual != logical:
                    shds_header.moveSection(visual, logical)

            for column, width in enumerate(default_widths):
                if column < table.columnCount():
                    table.setColumnWidth(column, width)
            for column, hidden in enumerate(default_hidden):
                if column < table.columnCount():
                    table.setColumnHidden(column, hidden)
        finally:
            shds_header.blockSignals(previous_block)

    saved_state = window.settings.value(settings_key)
    if saved_state:
        previous_block = shds_header.blockSignals(True)
        try:
            restored = shds_header.restoreState(saved_state)
        finally:
            shds_header.blockSignals(previous_block)
        if not restored:
            apply_shds_defaults()
        else:
            # Columns already hidden by the application are implementation
            # details and must not reappear because of stale saved state.
            for column, hidden in enumerate(default_hidden):
                if hidden and column < table.columnCount():
                    table.setColumnHidden(column, True)

    def save_shds_header(*_args) -> None:
        window.settings.setValue(settings_key, shds_header.saveState())

    def reset_shds_header() -> None:
        apply_shds_defaults()
        window.settings.remove(settings_key)

    shds_header.sectionMoved.connect(save_shds_header)
    shds_header.sectionResized.connect(save_shds_header)

    view_menu = None
    for menu_action in window.menuBar().actions():
        menu = menu_action.menu()
        if isinstance(menu, QMenu) and menu.title() == "Вид":
            view_menu = menu
            break
    if view_menu is None:
        view_menu = window.menuBar().addMenu("Вид")

    reset_action = QAction("Сбросить колонки ШДС", window)
    reset_action.triggered.connect(reset_shds_header)
    view_menu.addAction(reset_action)

    window.shds_custom_header = shds_header
    window.shds_default_widths = default_widths
    window.shds_default_hidden = default_hidden
    window.reset_shds_columns = reset_shds_header
    window.reset_shds_columns_action = reset_action

    _install_directory_action_panel(window)
    window._custom_workspace_ui_installed = True
