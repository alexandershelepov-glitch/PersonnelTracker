"""Read-only reporting facade for PersonnelTracker v0.9.1.

The module does not introduce personnel business rules.  It asks existing
services for already-calculated data, shapes rows for display/export and
provides a reusable CSV/TSV helper for later reports.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from services import PersonnelService


UNASSIGNED_UNIT = "Не назначен"
EMPTY_VALUE = "—"

ROSTER_COLUMNS: tuple[tuple[str, str], ...] = (
    ("fio", "ФИО"),
    ("personnel_no", "Табельный номер"),
    ("unit_number", "№ штатной единицы"),
    ("department", "Подразделение"),
    ("section", "Отделение"),
    ("group_name", "Группа"),
    ("position", "Должность"),
    ("schedule_type", "График"),
)


class ReportExportError(ValueError):
    """Raised when a report file cannot be written."""


@dataclass(frozen=True)
class ReportTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class RosterRow:
    fio: str
    personnel_no: str
    unit_number: str
    department: str
    section: str
    group_name: str
    position: str
    schedule_type: str

    def values(self) -> tuple[str, ...]:
        return (
            self.fio,
            self.personnel_no,
            self.unit_number,
            self.department,
            self.section,
            self.group_name,
            self.position,
            self.schedule_type,
        )


def roster_headers() -> tuple[str, ...]:
    return tuple(title for _key, title in ROSTER_COLUMNS)


def format_report_date(value: str | None) -> str:
    """Format an ISO date as ДД.ММ.ГГГГ for future dated reports."""
    if not value:
        return ""
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def default_roster_csv_name(day: date | None = None) -> str:
    when = day or date.today()
    return f"Личный_состав_{when.isoformat()}.csv"


def _display(value: object | None, empty: str = EMPTY_VALUE) -> str:
    text = str(value or "").strip()
    return text if text else empty


def render_csv(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(list(headers))
    for row in rows:
        writer.writerow(list(row))
    return buffer.getvalue()


def write_csv(destination: str | Path, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> Path:
    target = Path(destination).expanduser().resolve()
    if target.suffix.lower() != ".csv":
        target = target.with_suffix(".csv")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("w", encoding="utf-8-sig", newline="") as stream:
            stream.write(render_csv(headers, rows))
    except OSError as exc:
        raise ReportExportError("Не удалось сохранить CSV-файл.") from exc
    return target


def render_tsv(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")

    lines = ["\t".join(cell(header) for header in headers)]
    for row in rows:
        lines.append("\t".join(cell(value) for value in row))
    return "\n".join(lines)


class PersonnelRosterReport:
    """Active-employee roster using canonical staff-unit organisation fields."""

    def __init__(self, personnel: PersonnelService):
        self.personnel = personnel

    def rows(self) -> tuple[RosterRow, ...]:
        result: list[RosterRow] = []
        for person in self.personnel.list_employees(include_archived=False):
            details = self.personnel.get_employee(int(person["id"]))
            if details is None:
                continue
            result.append(self._row_from_employee(details))
        return tuple(result)

    def table(self) -> ReportTable:
        rows = self.rows()
        return ReportTable(roster_headers(), tuple(row.values() for row in rows))

    def _row_from_employee(self, details) -> RosterRow:
        unit_number = UNASSIGNED_UNIT
        unit_id = details["staff_unit_id"]
        if unit_id:
            unit = self.personnel.staff_unit(int(unit_id))
            if unit is not None and str(unit["unit_number"] or "").strip():
                unit_number = str(unit["unit_number"]).strip()
        schedule = str(details["schedule_type"] or "").strip() or "Не задан"
        return RosterRow(
            fio=str(details["fio"] or "").strip(),
            personnel_no=str(details["personnel_no"] or "").strip(),
            unit_number=unit_number,
            department=_display(details["effective_department"]),
            section=_display(details["effective_section"]),
            group_name=_display(details["effective_group"]),
            position=_display(details["effective_position"]),
            schedule_type=schedule,
        )
