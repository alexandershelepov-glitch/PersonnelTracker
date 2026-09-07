"""Employee profile workspace for PersonnelTracker v0.8.3-D.

This module deliberately reuses the proven EmployeeDialog fields, save logic,
photo handling and record editors.  It only reorganises their presentation and
adds read-only assignment / chronological views backed by the existing data.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _human_date(value: str | None) -> str:
    if not value:
        return "—"
    raw = str(value)
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed.strftime("%d.%m.%Y")
    except ValueError:
        try:
            return date.fromisoformat(raw[:10]).strftime("%d.%m.%Y")
        except ValueError:
            return raw


def install_employee_profile_ui(window: Any) -> None:
    """Replace the legacy employee card with a profile-oriented presentation.

    The replacement is a subclass of the legacy dialog, so every existing
    caller (MainWindow, Today, Composition, unassigned list) continues to use
    the same persistence and editing code after ``ui.EmployeeDialog`` is
    patched at runtime.
    """
    import ui as ui_module
    from assignment_history import AssignmentHistoryService
    from temporal_snapshot import TemporalPersonnelService
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    if getattr(window, "_employee_profile_ui_installed", False):
        return

    LegacyEmployeeDialog = ui_module.EmployeeDialog
    if getattr(LegacyEmployeeDialog, "_v083_profile_dialog", False):
        # A second MainWindow may be created in the same process (tests,
        # restore/restart shells).  The global class is already patched, but
        # this particular window still needs the public reference consumed by
        # the later polish/theme layers.
        window.employee_profile_dialog_class = LegacyEmployeeDialog
        window._employee_profile_ui_installed = True
        return

    class EmployeeProfileDialog(LegacyEmployeeDialog):
        _v083_profile_dialog = True

        def __init__(self, service, employee_id: int | None = None, parent=None):
            self._profile_ready = False
            super().__init__(service, employee_id, parent)
            self.setWindowTitle("Профиль работника")
            self.setMinimumSize(760, 540)
            self._assignment_history = AssignmentHistoryService(service.db)
            self._temporal_service = TemporalPersonnelService(service.db, history=self._assignment_history)
            self._build_profile_shell()
            self._profile_ready = True
            self._refresh_profile_header()
            self._refresh_profile_views()

        # Legacy __init__ calls these methods before the profile shell exists.
        # Guarding with _profile_ready lets us keep dynamic dispatch safely.
        def load_employee(self) -> None:
            LegacyEmployeeDialog.load_employee(self)
            if self._profile_ready:
                self._refresh_profile_header()
                self._refresh_profile_views()

        def refresh_records(self) -> None:
            LegacyEmployeeDialog.refresh_records(self)
            if self._profile_ready:
                self._refresh_profile_views()

        def delete_weapon(self):
            # Fix the legacy self-recursion while preserving the existing
            # confirmation / delete_record implementation.
            self.delete_record("Оружие")

        def _build_profile_shell(self) -> None:
            root = self.layout()
            main_layout = self.main_tab.layout()

            # Keep the existing summary card but make it a persistent profile
            # header above the tabs instead of burying it inside "Основное".
            profile_card = None
            for group in self.main_tab.findChildren(QGroupBox):
                if group.title() == "Карточка работника":
                    profile_card = group
                    break
            if profile_card is not None:
                main_layout.removeWidget(profile_card)
                profile_card.setTitle("Профиль работника")
                root.insertWidget(0, profile_card)
                layout = profile_card.layout()
                self.photo.setParent(profile_card)
                layout.removeWidget(self.photo)
                layout.addWidget(self.photo, 0, 0, 7, 1)
                self.profile_phone = QLabel("Телефон: —")
                self.profile_schedule = QLabel("График: —")
                self.profile_status = QLabel("Статус: —")
                self.profile_status.setWordWrap(True)
                self.profile_status.setObjectName("secondaryText")
                layout.addWidget(self.profile_phone, 5, 1)
                layout.addWidget(self.profile_schedule, 6, 1)
                layout.addWidget(self.profile_status, 5, 2, 2, 1)
                self.header_meta.setWordWrap(True)
            else:
                self.profile_phone = QLabel()
                self.profile_schedule = QLabel()
                self.profile_status = QLabel()

            # The detailed form remains editable, but routine journals move out
            # of the top-level tab strip into user-facing workflow groups.
            self.tabs.setTabText(0, "Данные")
            for group in self.main_tab.findChildren(QGroupBox):
                if group.title() == "Контроль":
                    group.hide()

            legacy_tabs: dict[str, QWidget] = {}
            for index in range(self.tabs.count() - 1, 0, -1):
                name = self.tabs.tabText(index)
                widget = self.tabs.widget(index)
                self.tabs.removeTab(index)
                legacy_tabs[name] = widget
            self._profile_record_tabs = legacy_tabs

            events_tab = legacy_tabs["Отсутствия"]
            self.tabs.addTab(events_tab, "События")

            checks_page = QWidget()
            checks_root = QVBoxLayout(checks_page)
            checks_root.setContentsMargins(0, 0, 0, 0)
            checks = QTabWidget()
            self.profile_checks_tabs = checks
            for name in ("Медкомиссия", "Периодическая проверка", "Обучение"):
                checks.addTab(legacy_tabs[name], name)
            checks_root.addWidget(checks)
            self.profile_checks_page = checks_page
            self.tabs.addTab(checks_page, "Проверки и обучение")

            weapons_tab = legacy_tabs["Оружие"]
            self.tabs.addTab(weapons_tab, "Вооружение")

            self.profile_assignments_page = QWidget()
            assignments_root = QVBoxLayout(self.profile_assignments_page)
            assignments_root.setContentsMargins(8, 10, 8, 8)
            self.profile_assignment_summary = QLabel()
            self.profile_assignment_summary.setWordWrap(True)
            assignments_root.addWidget(self.profile_assignment_summary)
            assignment_hint = QLabel(
                "История назначений ведётся с момента включения учёта v0.8; более ранние периоды приложение не выдумывает."
            )
            assignment_hint.setObjectName("secondaryText")
            assignment_hint.setWordWrap(True)
            assignments_root.addWidget(assignment_hint)
            self.profile_assignment_table = QTableWidget(0, 6)
            self.profile_assignment_table.setHorizontalHeaderLabels(
                ["С", "До", "ШЕ №", "Подразделение", "Отделение / группа", "Должность"]
            )
            self._prepare_readonly_table(self.profile_assignment_table)
            assignments_root.addWidget(self.profile_assignment_table, 1)
            self.tabs.addTab(self.profile_assignments_page, "Назначения")

            self.profile_history_page = QWidget()
            history_root = QVBoxLayout(self.profile_history_page)
            history_root.setContentsMargins(8, 10, 8, 8)
            history_hint = QLabel(
                "Общий хронологический журнал: события, проверки, обучение, вооружение и штатные назначения."
            )
            history_hint.setObjectName("secondaryText")
            history_hint.setWordWrap(True)
            history_root.addWidget(history_hint)
            self.profile_history_table = QTableWidget(0, 4)
            self.profile_history_table.setHorizontalHeaderLabels(
                ["Дата", "Раздел", "Запись", "Детали"]
            )
            self._prepare_readonly_table(self.profile_history_table)
            history_root.addWidget(self.profile_history_table, 1)
            self.tabs.addTab(self.profile_history_page, "История")

            # Make the return action explicit in the profile itself. Existing
            # callers may already rename it; this is idempotent.
            for button in self.findChildren(QPushButton):
                if button.text() == "Закрыть":
                    button.setText("← Назад")

        @staticmethod
        def _prepare_readonly_table(table: QTableWidget) -> None:
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectItems)
            table.setSelectionMode(QTableWidget.ExtendedSelection)
            table.setAlternatingRowColors(True)
            table.verticalHeader().hide()
            table.horizontalHeader().setStretchLastSection(True)

        def open_record_tab(self, name: str) -> None:
            if not getattr(self, "_profile_ready", False):
                return LegacyEmployeeDialog.open_record_tab(self, name)
            if name in {"Медкомиссия", "Периодическая проверка", "Обучение"}:
                self.tabs.setCurrentWidget(self.profile_checks_page)
                widget = self._profile_record_tabs.get(name)
                if widget is not None:
                    self.profile_checks_tabs.setCurrentWidget(widget)
                return
            mapping = {
                "Отсутствия": self._profile_record_tabs.get("Отсутствия"),
                "Оружие": self._profile_record_tabs.get("Оружие"),
            }
            widget = mapping.get(name)
            if widget is not None:
                self.tabs.setCurrentWidget(widget)
                return
            LegacyEmployeeDialog.open_record_tab(self, name)

        def _current_status_text(self) -> str:
            if not self.employee_id:
                return self.employment_status.currentText() if hasattr(self, "employment_status") else "—"
            try:
                today = date.today().isoformat()
                state = next(
                    (row for row in self._temporal_service.states(today) if row.employee_id == self.employee_id),
                    None,
                )
                if state is not None:
                    text = state.status_text
                    if state.location:
                        text += f" · {state.location}"
                    return text
            except Exception:
                pass
            return self.current_daily_status or self.employment_status.currentText() or "—"

        def _refresh_profile_header(self) -> None:
            if not hasattr(self, "profile_phone"):
                return
            number = self.personnel_no.text().strip() or "—"
            self.header_meta.setText(f"Табельный №: {number}")
            self.profile_phone.setText(f"Телефон: {self.phone.text().strip() or '—'}")
            self.profile_schedule.setText(f"График: {self.schedule_type.currentText() or 'Не задан'}")
            self.profile_status.setText(f"Статус на сегодня: {self._current_status_text()}")

        def _refresh_profile_views(self) -> None:
            if not getattr(self, "_profile_ready", False) or not self.employee_id:
                if hasattr(self, "profile_assignment_table"):
                    self.profile_assignment_table.setRowCount(0)
                    self.profile_history_table.setRowCount(0)
                    self.profile_assignment_summary.setText("Сначала сохраните карточку работника.")
                return
            person = self.service.get_employee(self.employee_id)
            self.profile_assignment_summary.setText(
                "Текущее назначение: " + self.service.assignment_status_text(person)
            )
            assignment_rows = list(self._assignment_history.list_history(self.employee_id))
            self.profile_assignment_table.setRowCount(len(assignment_rows))
            for row_index, item in enumerate(assignment_rows):
                values = [
                    _human_date(item["start_at"]),
                    _human_date(item["end_at"]) if item["end_at"] else "по настоящее время",
                    item["unit_number"] or "—",
                    item["department"] or "—",
                    " / ".join(part for part in (item["section"], item["group_name"]) if part) or "—",
                    item["position"] or "—",
                ]
                for column, value in enumerate(values):
                    self.profile_assignment_table.setItem(row_index, column, QTableWidgetItem(str(value)))
            self.profile_assignment_table.resizeColumnsToContents()
            self._refresh_chronology(assignment_rows)

        def _refresh_chronology(self, assignment_rows) -> None:
            entries: list[tuple[str, str, str, str]] = []

            for event in self.service.events_for_employee(self.employee_id):
                title = event["event_type"] + (f" / {event['subtype']}" if event["subtype"] else "")
                period = f"{_human_date(event['start_date'])} — {_human_date(event['end_date'])}"
                details = " · ".join(
                    part for part in (period, event["location"] or "", event["notes"] or "") if part
                )
                entries.append((str(event["start_date"] or ""), "События", title, details))

            for record in self.service.list_simple_history("medical_checks", self.employee_id):
                entries.append((str(record["check_date"] or ""), "Проверки", "Медкомиссия", record["notes"] or "—"))
            for record in self.service.list_simple_history("periodic_checks", self.employee_id):
                details = " · ".join(part for part in (record["result"] or "", record["notes"] or "") if part) or "—"
                entries.append((str(record["check_date"] or ""), "Проверки", "Периодическая проверка", details))
            for record in self.service.list_simple_history("trainings", self.employee_id):
                details = " · ".join(
                    part for part in (record["order_ref"] or "", record["certificate"] or "", record["notes"] or "") if part
                ) or "—"
                entries.append((str(record["training_date"] or ""), "Обучение", record["specialty"] or "Обучение", details))
            for record in self.service.list_simple_history("weapons", self.employee_id):
                weapon_date = str(record["assignment_date"] or "") if "assignment_date" in record.keys() else ""
                entries.append((weapon_date, "Вооружение", record["weapon_type"] or "Оружие", f"№ {record['serial_number'] or '—'}"))
            for record in assignment_rows:
                details = " · ".join(
                    part for part in (
                        f"ШЕ № {record['unit_number']}" if record["unit_number"] else "",
                        record["section"] or "",
                        record["group_name"] or "",
                    ) if part
                ) or "—"
                entries.append((str(record["start_at"] or ""), "Назначения", record["position"] or "Штатное назначение", details))

            entries.sort(key=lambda item: item[0], reverse=True)
            self.profile_history_table.setRowCount(len(entries))
            for row_index, entry in enumerate(entries):
                values = [_human_date(entry[0]), entry[1], entry[2], entry[3]]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(str(value or "—"))
                    cell.setToolTip(str(value or "—"))
                    self.profile_history_table.setItem(row_index, column, cell)
            self.profile_history_table.resizeColumnsToContents()

    EmployeeProfileDialog.__name__ = "EmployeeDialog"
    EmployeeProfileDialog.__qualname__ = "EmployeeDialog"
    ui_module.EmployeeDialog = EmployeeProfileDialog
    window.employee_profile_dialog_class = EmployeeProfileDialog
    window._employee_profile_ui_installed = True
