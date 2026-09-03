from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from config import APP_NAME
from database import Database


HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS staff_assignments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
 staff_unit_id INTEGER REFERENCES staff_units(id) ON DELETE SET NULL,
 employee_fio TEXT NOT NULL,
 employee_personnel_no TEXT NOT NULL,
 unit_number TEXT NOT NULL,
 department TEXT NOT NULL DEFAULT '',
 section TEXT NOT NULL DEFAULT '',
 group_name TEXT,
 position TEXT NOT NULL DEFAULT '',
 start_at TEXT NOT NULL,
 end_at TEXT,
 source TEXT NOT NULL DEFAULT 'assignment',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(end_at IS NULL OR end_at >= start_at)
);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_employee
 ON staff_assignments(employee_id,start_at,end_at);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_unit
 ON staff_assignments(staff_unit_id,start_at,end_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_assignments_open_employee
 ON staff_assignments(employee_id) WHERE end_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_assignments_open_unit
 ON staff_assignments(staff_unit_id)
 WHERE end_at IS NULL AND staff_unit_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_staff_assignment_insert
AFTER INSERT ON staff_units
WHEN NEW.employee_id IS NOT NULL
BEGIN
 INSERT INTO staff_assignments(
  employee_id,staff_unit_id,employee_fio,employee_personnel_no,
  unit_number,department,section,group_name,position,start_at,source
 )
 SELECT NEW.employee_id,NEW.id,p.fio,p.personnel_no,
        NEW.unit_number,NEW.department,NEW.section,NEW.group_name,NEW.position,
        strftime('%Y-%m-%dT%H:%M:%f','now','localtime'),'assignment'
 FROM employees p WHERE p.id=NEW.employee_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_staff_assignment_occupant_change
AFTER UPDATE OF employee_id ON staff_units
WHEN OLD.employee_id IS NOT NEW.employee_id
BEGIN
 UPDATE staff_assignments
 SET end_at=strftime('%Y-%m-%dT%H:%M:%f','now','localtime')
 WHERE staff_unit_id=OLD.id AND employee_id=OLD.employee_id AND end_at IS NULL;

 INSERT INTO staff_assignments(
  employee_id,staff_unit_id,employee_fio,employee_personnel_no,
  unit_number,department,section,group_name,position,start_at,source
 )
 SELECT NEW.employee_id,NEW.id,p.fio,p.personnel_no,
        NEW.unit_number,NEW.department,NEW.section,NEW.group_name,NEW.position,
        strftime('%Y-%m-%dT%H:%M:%f','now','localtime'),'assignment'
 FROM employees p WHERE NEW.employee_id IS NOT NULL AND p.id=NEW.employee_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_staff_assignment_unit_change
AFTER UPDATE OF unit_number,department,section,group_name,position ON staff_units
WHEN NEW.employee_id IS NOT NULL
 AND OLD.employee_id IS NEW.employee_id
 AND (
  OLD.unit_number IS NOT NEW.unit_number OR OLD.department IS NOT NEW.department OR
  OLD.section IS NOT NEW.section OR OLD.group_name IS NOT NEW.group_name OR
  OLD.position IS NOT NEW.position
 )
BEGIN
 UPDATE staff_assignments
 SET end_at=strftime('%Y-%m-%dT%H:%M:%f','now','localtime')
 WHERE staff_unit_id=NEW.id AND employee_id=NEW.employee_id AND end_at IS NULL;

 INSERT INTO staff_assignments(
  employee_id,staff_unit_id,employee_fio,employee_personnel_no,
  unit_number,department,section,group_name,position,start_at,source
 )
 SELECT NEW.employee_id,NEW.id,p.fio,p.personnel_no,
        NEW.unit_number,NEW.department,NEW.section,NEW.group_name,NEW.position,
        strftime('%Y-%m-%dT%H:%M:%f','now','localtime'),'unit-change'
 FROM employees p WHERE p.id=NEW.employee_id;
END;
"""


def ensure_assignment_history(db: Database) -> str:
    """Create v0.8 history without inventing any pre-v0.8 past state.

    Existing occupied units become a baseline only from the moment this feature
    is first enabled. Earlier dates are intentionally unavailable.
    """
    with db.connect() as connection:
        existed = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='staff_assignments'"
        ).fetchone() is not None
        connection.executescript(HISTORY_SCHEMA)
        started_at_row = connection.execute(
            "SELECT value FROM settings WHERE key='history_tracking_started_at'"
        ).fetchone()
        if started_at_row:
            return str(started_at_row['value'])

        started_at = connection.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%f','now','localtime')"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO settings(key,value) VALUES('history_tracking_started_at',?)",
            (started_at,),
        )
        if not existed:
            connection.execute(
                """
                INSERT OR IGNORE INTO staff_assignments(
                    employee_id,staff_unit_id,employee_fio,employee_personnel_no,
                    unit_number,department,section,group_name,position,start_at,source
                )
                SELECT p.id,u.id,p.fio,p.personnel_no,u.unit_number,u.department,u.section,
                       u.group_name,u.position,?,'baseline'
                FROM staff_units u
                JOIN employees p ON p.id=u.employee_id
                WHERE p.employment_status='Работает'
                """,
                (started_at,),
            )
        return str(started_at)


@dataclass(frozen=True)
class HistorySummary:
    tracking_started_at: str
    total_records: int
    open_assignments: int


class AssignmentHistoryService:
    def __init__(self, db: Database):
        self.db = db
        self.tracking_started_at = ensure_assignment_history(db)

    @property
    def tracking_started_date(self) -> date:
        return date.fromisoformat(self.tracking_started_at[:10])

    def summary(self) -> HistorySummary:
        with self.db.connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM staff_assignments").fetchone()[0])
            opened = int(connection.execute("SELECT COUNT(*) FROM staff_assignments WHERE end_at IS NULL").fetchone()[0])
        return HistorySummary(self.tracking_started_at, total, opened)

    def list_history(self, employee_id: int | None = None):
        sql = "SELECT * FROM staff_assignments"
        params: list[Any] = []
        if employee_id is not None:
            sql += " WHERE employee_id=?"
            params.append(int(employee_id))
        sql += " ORDER BY start_at DESC, id DESC"
        with self.db.connect() as connection:
            return connection.execute(sql, params).fetchall()

    def snapshot(self, target_date: str):
        try:
            chosen = date.fromisoformat(target_date)
        except ValueError as exc:
            raise ValueError("Некорректная дата среза.") from exc
        if chosen < self.tracking_started_date:
            raise ValueError(
                "История назначений ведётся только с "
                + self.tracking_started_date.strftime("%d.%m.%Y")
                + ". Более раннее состояние приложение не будет выдумывать."
            )
        if chosen > date.today():
            raise ValueError("Нельзя построить исторический срез на будущую дату.")
        cutoff = target_date + "T23:59:59.999"
        with self.db.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM staff_assignments
                WHERE start_at<=? AND (end_at IS NULL OR end_at>?)
                ORDER BY department,section,group_name,unit_number
                """,
                (cutoff, cutoff),
            ).fetchall()


def _format_moment(value: str | None) -> str:
    if not value:
        return "по настоящее время"
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


def install_assignment_history_features(window: Any) -> None:
    """Add the first v0.8 UI without modifying the large legacy ui.py file."""
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtWidgets import (
        QComboBox,
        QDateEdit,
        QDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )

    service = AssignmentHistoryService(window.db)
    window.assignment_history = service

    # A restored v0.7 backup does not yet contain the v0.8 table. Reinstall it
    # immediately after restore rather than requiring an application restart.
    manager = getattr(window, "backup_manager", None)
    if manager is not None and not getattr(manager, "_v08_history_wrapped", False):
        original_restore = manager.restore_backup

        def restore_with_history(*args, **kwargs):
            result = original_restore(*args, **kwargs)
            service.tracking_started_at = ensure_assignment_history(window.db)
            return result

        manager.restore_backup = restore_with_history
        manager._v08_history_wrapped = True

    class HistoryDialog(QDialog):
        HEADERS = [
            "С", "До", "Таб. №", "ФИО", "ШЕ №", "Подразделение",
            "Отделение", "Группа", "Должность", "Запись",
        ]

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("История штатных назначений")
            self.resize(1180, 650)
            root = QVBoxLayout(self)
            controls = QHBoxLayout()
            self.employee = QComboBox()
            self.employee.addItem("Все работники", None)
            with window.db.connect() as connection:
                people = connection.execute(
                    "SELECT id,fio,personnel_no FROM employees ORDER BY fio COLLATE NOCASE"
                ).fetchall()
            for person in people:
                self.employee.addItem(
                    f"{person['fio']} ({person['personnel_no']})", int(person['id'])
                )
            self.employee.currentIndexChanged.connect(self.reload)
            controls.addWidget(QLabel("Работник:"))
            controls.addWidget(self.employee, 1)
            controls.addStretch()
            root.addLayout(controls)
            self.table = QTableWidget(0, len(self.HEADERS))
            self.table.setHorizontalHeaderLabels(self.HEADERS)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)
            self.table.horizontalHeader().setStretchLastSection(True)
            root.addWidget(self.table, 1)
            close = QPushButton("Закрыть")
            close.clicked.connect(self.accept)
            bottom = QHBoxLayout(); bottom.addStretch(); bottom.addWidget(close); root.addLayout(bottom)
            self.reload()

        def reload(self):
            rows = service.list_history(self.employee.currentData())
            self.table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                source = {
                    "baseline": "Начальное состояние v0.8",
                    "unit-change": "Изменение ШЕ",
                    "assignment": "Назначение",
                }.get(row['source'], row['source'])
                values = [
                    _format_moment(row['start_at']), _format_moment(row['end_at']),
                    row['employee_personnel_no'], row['employee_fio'], row['unit_number'],
                    row['department'] or "—", row['section'] or "—", row['group_name'] or "—",
                    row['position'] or "—", source,
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    self.table.setItem(row_index, column, item)
            self.table.resizeColumnsToContents()

    class SnapshotDialog(QDialog):
        HEADERS = ["ШЕ №", "Подразделение", "Отделение", "Группа", "Должность", "ФИО", "Таб. №"]

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Штатные назначения на дату")
            self.resize(1050, 620)
            root = QVBoxLayout(self)
            controls = QHBoxLayout()
            self.when = QDateEdit(calendarPopup=True)
            self.when.setDisplayFormat("dd.MM.yyyy")
            self.when.setMinimumDate(QDate.fromString(service.tracking_started_date.isoformat(), "yyyy-MM-dd"))
            self.when.setMaximumDate(QDate.currentDate())
            self.when.setDate(QDate.currentDate())
            refresh = QPushButton("Показать")
            refresh.clicked.connect(self.reload)
            controls.addWidget(QLabel("Состояние на конец дня:"))
            controls.addWidget(self.when)
            controls.addWidget(refresh)
            controls.addStretch()
            root.addLayout(controls)
            hint = QLabel(
                "Срез показывает назначение работников на конец выбранного дня. "
                "История до начала учёта v0.8 намеренно не восстанавливается задним числом."
            )
            hint.setWordWrap(True)
            root.addWidget(hint)
            self.table = QTableWidget(0, len(self.HEADERS))
            self.table.setHorizontalHeaderLabels(self.HEADERS)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)
            self.table.horizontalHeader().setStretchLastSection(True)
            root.addWidget(self.table, 1)
            close = QPushButton("Закрыть"); close.clicked.connect(self.accept)
            bottom = QHBoxLayout(); bottom.addStretch(); bottom.addWidget(close); root.addLayout(bottom)
            self.reload()

        def reload(self):
            iso = self.when.date().toString("yyyy-MM-dd")
            try:
                rows = service.snapshot(iso)
            except ValueError as exc:
                QMessageBox.warning(self, "Срез назначений", str(exc))
                return
            self.table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                values = [
                    row['unit_number'], row['department'] or "—", row['section'] or "—",
                    row['group_name'] or "—", row['position'] or "—",
                    row['employee_fio'], row['employee_personnel_no'],
                ]
                for column, value in enumerate(values):
                    self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
            self.table.resizeColumnsToContents()

    def open_history():
        HistoryDialog(window).exec()

    def open_snapshot():
        SnapshotDialog(window).exec()

    page = window.pages.widget(4)
    layout = page.layout()
    box = QGroupBox("История штатных назначений — v0.8")
    box_layout = QVBoxLayout(box)
    summary = service.summary()
    started = service.tracking_started_date.strftime("%d.%m.%Y")
    description = QLabel(
        f"Учёт истории начат {started}. Текущих назначений: {summary.open_assignments}. "
        "Каждое последующее назначение, освобождение ШЕ и изменение её служебных данных фиксируется автоматически."
    )
    description.setWordWrap(True)
    box_layout.addWidget(description)
    buttons = QHBoxLayout()
    history_button = QPushButton("История назначений")
    history_button.setProperty("role", "primary")
    history_button.clicked.connect(open_history)
    snapshot_button = QPushButton("Срез назначений на дату")
    snapshot_button.clicked.connect(open_snapshot)
    buttons.addWidget(history_button); buttons.addWidget(snapshot_button); buttons.addStretch()
    box_layout.addLayout(buttons)
    layout.insertWidget(max(0, layout.count() - 1), box)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addSeparator()
        service_menu.addAction("История штатных назначений", open_history)
        service_menu.addAction("Срез назначений на дату", open_snapshot)

    window.setWindowTitle(APP_NAME + " — версия 0.8")
    for label in window.findChildren(QLabel):
        if label.text() in {"v0.6", "v0.7"}:
            label.setText("v0.8")
