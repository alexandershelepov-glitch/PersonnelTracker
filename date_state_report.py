"""Read-only personnel state report for one historical date."""
from __future__ import annotations

from dataclasses import dataclass

from reports import EMPTY_VALUE, ReportTable
from temporal_snapshot import TemporalPersonnelService


DATE_STATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("unit_number", "ШЕ №"),
    ("department", "Подразделение"),
    ("section", "Отделение"),
    ("group_name", "Группа"),
    ("position", "Должность"),
    ("fio", "ФИО"),
    ("personnel_no", "Табельный номер"),
    ("schedule_type", "График"),
    ("status", "Статус"),
    ("location", "Место / объект"),
    ("availability", "Доступность"),
)


def date_state_headers() -> tuple[str, ...]:
    return tuple(title for _key, title in DATE_STATE_COLUMNS)


def default_date_state_csv_name(target_date: str, unavailable_only: bool = False) -> str:
    prefix = "Недоступные" if unavailable_only else "Состояние_личного_состава"
    return f"{prefix}_{target_date}.csv"


def _display(value: object | None, empty: str = EMPTY_VALUE) -> str:
    text = str(value or "").strip()
    return text if text else empty


@dataclass(frozen=True)
class DateStateRow:
    unit_number: str
    department: str
    section: str
    group_name: str
    position: str
    fio: str
    personnel_no: str
    schedule_type: str
    status: str
    location: str
    availability: str

    def values(self) -> tuple[str, ...]:
        return (
            self.unit_number,
            self.department,
            self.section,
            self.group_name,
            self.position,
            self.fio,
            self.personnel_no,
            self.schedule_type,
            self.status,
            self.location,
            self.availability,
        )


class PersonnelDateStateReport:
    """Shape TemporalPersonnelService output for display and export."""

    def __init__(self, temporal: TemporalPersonnelService):
        self.temporal = temporal

    def rows(self, target_date: str, unavailable_only: bool = False) -> tuple[DateStateRow, ...]:
        source = self.temporal.states(target_date)
        if unavailable_only:
            source = [row for row in source if row.availability == "Недоступен"]
        return tuple(
            DateStateRow(
                unit_number=_display(row.unit_number),
                department=_display(row.department),
                section=_display(row.section),
                group_name=_display(row.group_name),
                position=_display(row.position),
                fio=_display(row.fio),
                personnel_no=_display(row.personnel_no),
                schedule_type=_display(row.schedule_type, "Не задан"),
                status=_display(row.status_text),
                location=_display(row.location),
                availability=_display(row.availability),
            )
            for row in source
        )

    def table(self, target_date: str, unavailable_only: bool = False) -> ReportTable:
        rows = self.rows(target_date, unavailable_only=unavailable_only)
        return ReportTable(date_state_headers(), tuple(row.values() for row in rows))
