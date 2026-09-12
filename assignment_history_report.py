"""Read-only assignment history report for PersonnelTracker v0.9.1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from assignment_history import AssignmentHistoryService
from reports import EMPTY_VALUE, ReportTable

ASSIGNMENT_HISTORY_COLUMNS = (
    ("start_at", "С"),
    ("end_at", "До"),
    ("personnel_no", "Табельный номер"),
    ("fio", "ФИО"),
    ("unit_number", "№ штатной единицы"),
    ("department", "Подразделение"),
    ("section", "Отделение"),
    ("group_name", "Группа"),
    ("position", "Должность"),
    ("source", "Запись"),
)

SOURCE_LABELS = {
    "baseline": "Начальное состояние",
    "unit-change": "Изменение ШЕ",
    "assignment": "Назначение",
}
CURRENT_ASSIGNMENT = "по настоящее время"


def assignment_history_headers() -> tuple[str, ...]:
    return tuple(title for _key, title in ASSIGNMENT_HISTORY_COLUMNS)


def default_assignment_history_csv_name(day: date | None = None) -> str:
    chosen = day or date.today()
    return f"История_назначений_{chosen.isoformat()}.csv"


def _display(value: object | None) -> str:
    text = str(value or "").strip()
    return text if text else EMPTY_VALUE


def format_history_moment(value: object | None, *, open_ended: bool = False) -> str:
    if not value:
        return CURRENT_ASSIGNMENT if open_ended else EMPTY_VALUE
    text = str(value)
    try:
        return datetime.fromisoformat(text).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return text


@dataclass(frozen=True)
class AssignmentHistoryRow:
    start_at: str
    end_at: str
    personnel_no: str
    fio: str
    unit_number: str
    department: str
    section: str
    group_name: str
    position: str
    source: str

    def values(self) -> tuple[str, ...]:
        return (
            self.start_at, self.end_at, self.personnel_no, self.fio,
            self.unit_number, self.department, self.section, self.group_name,
            self.position, self.source,
        )


class AssignmentHistoryReport:
    def __init__(self, history: AssignmentHistoryService):
        self.history = history

    def rows(self, employee_id: int | None = None) -> tuple[AssignmentHistoryRow, ...]:
        result: list[AssignmentHistoryRow] = []
        for row in self.history.list_history(employee_id):
            raw_source = str(row["source"] or "").strip()
            result.append(AssignmentHistoryRow(
                start_at=format_history_moment(row["start_at"]),
                end_at=format_history_moment(row["end_at"], open_ended=True),
                personnel_no=_display(row["employee_personnel_no"]),
                fio=_display(row["employee_fio"]),
                unit_number=_display(row["unit_number"]),
                department=_display(row["department"]),
                section=_display(row["section"]),
                group_name=_display(row["group_name"]),
                position=_display(row["position"]),
                source=SOURCE_LABELS.get(raw_source, raw_source or EMPTY_VALUE),
            ))
        return tuple(result)

    def table(self, employee_id: int | None = None) -> ReportTable:
        rows = self.rows(employee_id)
        return ReportTable(assignment_history_headers(), tuple(row.values() for row in rows))
