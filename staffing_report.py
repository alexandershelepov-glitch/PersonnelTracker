"""Read-only staffing placement report for PersonnelTracker v0.9.1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from reports import EMPTY_VALUE, ReportTable
from services import PersonnelService


VACANCY_FIO = "ВАКАНСИЯ"
OCCUPIED_STATUS = "Занято"
VACANT_STATUS = "Вакансия"

STAFFING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("unit_number", "№ штатной единицы"),
    ("department", "Подразделение"),
    ("section", "Отделение"),
    ("group_name", "Группа"),
    ("position", "Должность"),
    ("fio", "ФИО"),
    ("personnel_no", "Табельный номер"),
    ("schedule_type", "График"),
    ("place_status", "Статус места"),
)


def staffing_headers() -> tuple[str, ...]:
    return tuple(title for _key, title in STAFFING_COLUMNS)


def default_staffing_csv_name(day: date | None = None) -> str:
    when = day or date.today()
    return f"Штатная_расстановка_{when.isoformat()}.csv"


def _display(value: object | None, empty: str = EMPTY_VALUE) -> str:
    text = str(value or "").strip()
    return text if text else empty


@dataclass(frozen=True)
class StaffingPlacementRow:
    unit_number: str
    department: str
    section: str
    group_name: str
    position: str
    fio: str
    personnel_no: str
    schedule_type: str
    place_status: str

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
            self.place_status,
        )


class StaffingPlacementReport:
    """All staffing units with active occupant or vacancy state."""

    def __init__(self, personnel: PersonnelService):
        self.personnel = personnel

    def rows(self) -> tuple[StaffingPlacementRow, ...]:
        result: list[StaffingPlacementRow] = []
        for unit in self.personnel.list_staff_units():
            active = bool(unit["employee_id"] and unit["employment_status"] == "Работает")
            result.append(
                StaffingPlacementRow(
                    unit_number=_display(unit["unit_number"]),
                    department=_display(unit["department"]),
                    section=_display(unit["section"]),
                    group_name=_display(unit["group_name"]),
                    position=_display(unit["position"]),
                    fio=_display(unit["fio"]) if active else VACANCY_FIO,
                    personnel_no=_display(unit["personnel_no"]) if active else EMPTY_VALUE,
                    schedule_type=_display(unit["schedule_type"]) if active else EMPTY_VALUE,
                    place_status=OCCUPIED_STATUS if active else VACANT_STATUS,
                )
            )
        return tuple(result)

    def table(self) -> ReportTable:
        rows = self.rows()
        return ReportTable(staffing_headers(), tuple(row.values() for row in rows))
