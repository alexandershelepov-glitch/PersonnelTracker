"""Operational day-state adapter for the v0.8.3 Today screen.

This module does not introduce new persistence or event rules.  It combines the
current SHDS with the existing events table and delegates schedule evaluation to
TemporalPersonnelService so the Today screen and v0.8.2 use the same 1/3, 5/2
and "requires review" semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from config import UNAVAILABLE_EVENT_TYPES
from services import PersonnelService
from temporal_snapshot import TemporalPersonnelService


@dataclass(frozen=True)
class TodayPersonState:
    employee_id: int
    fio: str
    personnel_no: str
    department: str
    section: str
    position: str
    status: str
    subtype: str
    location: str
    availability: str
    source: str
    event_id: int | None = None
    batch_id: str | None = None
    start_date: str = ""
    end_date: str = ""

    @property
    def status_text(self) -> str:
        return f"{self.status}: {self.subtype}" if self.subtype else self.status


@dataclass(frozen=True)
class TodaySnapshot:
    target_date: str
    staff: int
    listed: int
    present: int
    absent: int
    vacant: int
    needs_check: int
    rows: tuple[TodayPersonState, ...]

    @property
    def valid(self) -> bool:
        return self.staff == self.listed + self.vacant


class TodayStateService:
    """Build the operational picture for a selected day without new storage."""

    def __init__(self, personnel: PersonnelService, temporal: TemporalPersonnelService):
        self.personnel = personnel
        self.temporal = temporal

    def _events_for_day(self, target_date: str) -> dict[int, Any]:
        rows = [
            row for row in self.personnel.list_events()
            if str(row["start_date"]) <= target_date <= str(row["end_date"])
        ]
        result: dict[int, Any] = {}
        for row in rows:
            result.setdefault(int(row["employee_id"]), row)
        return result

    def snapshot(self, target_date: str) -> TodaySnapshot:
        target = date.fromisoformat(target_date)
        units = self.personnel.list_staff_units()
        occupied = [
            unit for unit in units
            if unit["employee_id"] and unit["employment_status"] == "Работает"
        ]
        people = {
            int(person["id"]): person
            for person in self.personnel.list_employees(include_archived=False)
        }
        events = self._events_for_day(target_date)
        states: list[TodayPersonState] = []

        for unit in occupied:
            employee_id = int(unit["employee_id"])
            person = people.get(employee_id)
            if person is None:
                continue
            event = events.get(employee_id)
            if event is not None:
                status = str(event["event_type"] or "")
                subtype = str(event["subtype"] or "")
                location = str(event["location"] or "")
                availability = "Недоступен" if status in UNAVAILABLE_EVENT_TYPES else "Доступен"
                source = "event"
                event_id = int(event["id"])
                batch_id = str(event["batch_id"] or "") or None
                start_date = str(event["start_date"] or "")
                end_date = str(event["end_date"] or "")
            else:
                # Reuse the v0.8.2 schedule resolver: 1/3, 5/2 and unknown
                # schedules therefore have one meaning across both screens.
                status, availability, source = self.temporal._schedule_state(person, target)
                subtype = ""
                location = ""
                event_id = None
                batch_id = None
                start_date = ""
                end_date = ""

            states.append(TodayPersonState(
                employee_id=employee_id,
                fio=str(person["fio"] or ""),
                personnel_no=str(person["personnel_no"] or ""),
                department=str(unit["department"] or person["department"] or ""),
                section=str(unit["section"] or person["section"] or ""),
                position=str(unit["position"] or person["position"] or ""),
                status=status,
                subtype=subtype,
                location=location,
                availability=availability,
                source=source,
                event_id=event_id,
                batch_id=batch_id,
                start_date=start_date,
                end_date=end_date,
            ))

        present = sum(row.availability == "Доступен" for row in states)
        absent = sum(row.availability == "Недоступен" for row in states)
        needs_check = sum(row.availability == "Требует проверки" for row in states)
        return TodaySnapshot(
            target_date=target_date,
            staff=len(units),
            listed=len(occupied),
            present=present,
            absent=absent,
            vacant=len(units) - len(occupied),
            needs_check=needs_check,
            rows=tuple(sorted(states, key=lambda row: row.fio.casefold())),
        )

    def duplicate_event_people(self, target_date: str) -> list[dict[str, Any]]:
        """Return people with more than one legacy event covering the day."""
        covering = [
            row for row in self.personnel.list_events()
            if str(row["start_date"]) <= target_date <= str(row["end_date"])
        ]
        grouped: dict[int, list[Any]] = {}
        for row in covering:
            grouped.setdefault(int(row["employee_id"]), []).append(row)
        result = []
        for employee_id, rows in grouped.items():
            if len(rows) < 2:
                continue
            person = self.personnel.get_employee(employee_id)
            result.append({
                "employee_id": employee_id,
                "fio": person["fio"] if person else f"ID {employee_id}",
                "detail": f"Пересекающихся событий: {len(rows)}",
            })
        return sorted(result, key=lambda item: str(item["fio"]).casefold())
