"""Final interface polish for PersonnelTracker v0.8.3-H.

This module is deliberately presentation-only.  It keeps the accepted v0.8.3
workflows and business logic intact while making the resulting desktop UI feel
like one coherent application: compact tables, consistent dates and tabs,
clear clickable affordances, calmer helper text and theme-aware event/status
colours.
"""
from __future__ import annotations

from types import MethodType
from typing import Any

from event_colors import event_background, event_foreground


def install_interface_polish(window: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QDateEdit,
        QHeaderView,
        QLabel,
        QPushButton,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableWidget,
        QTabWidget,
    )

    if getattr(window, "_interface_polish_installed", False):
        return

    class AccentLinkDelegate(QStyledItemDelegate):
        """Render a table column like a quiet link without adding button noise."""

        def paint(self, painter, option, index):
            styled = QStyleOptionViewItem(option)
            styled.font.setUnderline(True)
            if not (styled.state & QStyle.State_Selected):
                styled.palette.setColor(QPalette.Text, window.theme_manager.color("accent"))
            super().paint(painter, styled, index)

    class AvailabilityDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index):
            styled = QStyleOptionViewItem(option)
            value = str(index.data() or "")
            if not (styled.state & QStyle.State_Selected):
                if value == "Доступен":
                    styled.palette.setColor(QPalette.Text, window.theme_manager.color("success"))
                elif value == "Требует проверки":
                    styled.palette.setColor(QPalette.Text, window.theme_manager.color("warning"))
                elif value == "Недоступен":
                    styled.palette.setColor(QPalette.Text, window.theme_manager.color("muted"))
            super().paint(painter, styled, index)

    link_delegate = AccentLinkDelegate(window)
    availability_delegate = AvailabilityDelegate(window)
    window._interface_link_delegate = link_delegate
    window._interface_availability_delegate = availability_delegate

    def page_title(index: int, text: str) -> None:
        page = window.pages.widget(index)
        if page is None:
            return
        for label in page.findChildren(QLabel):
            if label.objectName() == "pageTitle":
                label.setText(text)
                break

    page_title(0, "Состав")
    page_title(2, "Планирование")
    page_title(4, "Настройки")

    # The product should speak in user terms, not implementation/version terms.
    for label in window.findChildren(QLabel):
        text = label.text()
        if "временного среза v0.8.2" in text:
            label.setText(
                "Состояние учитывает ШДС, зарегистрированные события и график на выбранный день. "
                "Если график не указан, сотрудник отмечается как требующий проверки."
            )
        elif text.startswith("Сотрудники расположены по строкам, дни месяца"):
            label.setText(
                "Нажмите ФИО — добавить событие работнику. Дважды нажмите пустой день — "
                "добавить событие на конкретную дату. Нажмите существующее событие — открыть его."
            )
        elif text.startswith("Выберите дату и отметьте работников вручную"):
            label.setText(
                "Выберите дату и отметьте нужных работников. Статус и доступность рассчитываются "
                "по тем же данным, что используются на экране «Сегодня»."
            )
        elif text.startswith("Программа только предлагает состав"):
            label.setText(
                "Программа предлагает состав по выбранным условиям и истории групповых назначений. "
                "Предложение можно свободно изменить до создания события."
            )

    def compact_table(table: QTableWidget, row_height: int = 30, header_height: int = 36) -> None:
        table.setWordWrap(False)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.verticalHeader().setDefaultSectionSize(row_height)
        table.verticalHeader().setMinimumSectionSize(row_height)
        table.verticalHeader().setMaximumSectionSize(row_height)
        table.horizontalHeader().setMinimumHeight(header_height)
        table.verticalScrollBar().setSingleStep(row_height)

    planner_people = getattr(window, "planning_people_table", None)
    planner_days = getattr(window, "planning_days_table", None)
    for table in window.findChildren(QTableWidget):
        if table is planner_people or table is planner_days:
            compact_table(table, 32, 56)
        else:
            compact_table(table)

    # Tables with many employees should remain dense and scannable.
    directory = getattr(window, "composition_directory_table", None)
    if directory is not None:
        directory.setItemDelegateForColumn(0, link_delegate)

    manual = getattr(window, "manual_team_table", None)
    if manual is not None:
        manual.setItemDelegateForColumn(8, availability_delegate)
        manual.horizontalHeader().setStretchLastSection(False)

    semi = getattr(window, "semi_auto_team_table", None)
    if semi is not None:
        semi.horizontalHeader().setStretchLastSection(False)

    if planner_people is not None:
        planner_people.setItemDelegateForColumn(0, link_delegate)
        planner_people.setToolTip("Нажмите на ФИО, чтобы добавить событие этому работнику.")

    today = getattr(window, "today_page", None)
    if today is not None:
        today.absent_table.setItemDelegateForColumn(0, link_delegate)
        today.shift_table.setItemDelegateForColumn(0, link_delegate)
        for table in (today.absent_table, today.shift_table):
            compact_table(table, 30, 36)

        # Keep the event type as a small semantic colour marker instead of
        # colouring the whole row on the operational dashboard.
        original_fill_absent = today._fill_absent

        def fill_absent(self, rows):
            original_fill_absent(rows)
            for row_index, person in enumerate(rows):
                event_cell = self.absent_table.item(row_index, 1)
                if event_cell is not None and getattr(person, "event_id", None):
                    event_cell.setBackground(event_background(person.status, window.theme_manager))
                    event_cell.setForeground(event_foreground(person.status, window.theme_manager))
            self.absent_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.absent_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.absent_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self.absent_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        today._fill_absent = MethodType(fill_absent, today)

        original_fill_shift = today._fill_shift

        def fill_shift(self, rows):
            original_fill_shift(rows)
            self.shift_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.shift_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.shift_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        today._fill_shift = MethodType(fill_shift, today)

        for frame in today.findChildren(type(today.attention_panel)):
            if frame.objectName() in {"todayMetric", "todaySection"}:
                frame.setMinimumHeight(72 if frame.objectName() == "todayMetric" else 0)

    # One compact date format everywhere the user edits a date.
    for date_edit in window.findChildren(QDateEdit):
        date_edit.setDisplayFormat("dd.MM.yyyy")

    # Tabs are work areas rather than decorative cards; keep them compact and
    # allow narrow windows to scroll instead of squeezing labels into noise.
    for tabs in window.findChildren(QTabWidget):
        tabs.setDocumentMode(True)
        tabs.tabBar().setUsesScrollButtons(True)
        tabs.tabBar().setElideMode(Qt.ElideRight)

    for button in window.findChildren(QPushButton):
        if button.property("role") == "primary":
            button.setMinimumHeight(34)
        if button.text().startswith("← Назад"):
            button.setProperty("backButton", True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMaximumWidth(112)
        elif button.property("navButton"):
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(36)

    # Employee profiles are created lazily, so polish the profile class itself
    # once and every future opening gets the same treatment.
    profile_class = getattr(window, "employee_profile_dialog_class", None)
    if profile_class is not None and not getattr(profile_class, "_v083_interface_polished", False):
        original_profile_init = profile_class.__init__

        def profile_init(dialog, *args, **kwargs):
            original_profile_init(dialog, *args, **kwargs)
            for label in dialog.findChildren(QLabel):
                text = label.text()
                if text.startswith("История назначений ведётся с момента включения учёта v0.8"):
                    label.setText(
                        "История назначений отображается с момента начала её ведения в приложении."
                    )
                elif text.startswith("Общий хронологический журнал"):
                    label.setText(
                        "События, проверки, обучение, вооружение и назначения в одном хронологическом списке."
                    )
            for table in dialog.findChildren(QTableWidget):
                compact_table(table)
            for tabs in dialog.findChildren(QTabWidget):
                tabs.setDocumentMode(True)
                tabs.tabBar().setUsesScrollButtons(True)
                tabs.tabBar().setElideMode(Qt.ElideRight)
            for date_edit in dialog.findChildren(QDateEdit):
                date_edit.setDisplayFormat("dd.MM.yyyy")
            for label in (
                getattr(dialog, "header_meta", None),
                getattr(dialog, "profile_phone", None),
                getattr(dialog, "profile_schedule", None),
                getattr(dialog, "profile_status", None),
            ):
                if label is not None:
                    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            for button in dialog.findChildren(QPushButton):
                if button.text().startswith("← Назад"):
                    button.setProperty("backButton", True)
                    button.setMaximumWidth(112)
                    button.setCursor(Qt.PointingHandCursor)
            dialog._v083_interface_polished_instance = True

        profile_class.__init__ = profile_init
        profile_class._v083_interface_polished = True

    def apply_theme_polish() -> None:
        accent = window.theme_manager.color("accent").name()
        hover = window.theme_manager.color("hover").name()
        for button in window.findChildren(QPushButton):
            if button.property("backButton"):
                button.setStyleSheet(
                    "QPushButton { border: none; background: transparent; "
                    f"color: {accent}; padding: 4px 2px; text-align: left; }} "
                    f"QPushButton:hover {{ background: {hover}; }}"
                )
        if today is not None:
            today.refresh()

    original_sync = window._sync_theme_controls

    def sync_theme() -> None:
        original_sync()
        apply_theme_polish()

    window._sync_theme_controls = sync_theme
    apply_theme_polish()
    window._interface_polish_installed = True
