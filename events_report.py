"""Read-only events report data layer for PersonnelTracker.

One row = one existing ``events`` row = one worker in one registered event.
All events are represented without deciding whether an event_type is an
"activity": events also hold vacations, sick leaves and other records.

No business rules are added.  The layer asks ``PersonnelService.list_events``
for the data and only:
  * filters rows to those overlapping the requested period;
  * marks a row as "Групповое"/"Одиночное" from ``batch_id`` semantics;
  * reports how many worker rows share the same ``batch_id``.
Worker organisation fields are intentionally NOT resolved from the current
assignment because they may be historically wrong for the event date.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from reports import EMPTY_VALUE, ReportTable, format_report_date
from services import PersonnelService

SINGLE_LABEL = "Одиночное"
GROUP_LABEL = "Групповое"

EVENTS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("start_date", "С"),
    ("end_date", "По"),
    ("event_type", "Тип события"),
    ("subtype", "Подтип"),
    ("location", "Место / объект"),
    ("basis", "Основание"),
    ("notes", "Примечание"),
    ("fio", "ФИО"),
    ("personnel_no", "Табельный номер"),
    ("format", "Формат"),
    ("participants", "Участников"),
)

PERIOD_ERROR = "Начало периода не может быть позже его окончания."


def events_headers() -> tuple[str, ...]:
    return tuple(title for _key, title in EVENTS_COLUMNS)


def _display(value: object | None, empty: str = EMPTY_VALUE) -> str:
    text = str(value or "").strip()
    return text if text else empty


@dataclass(frozen=True)
class EventsRow:
    start_date: str
    end_date: str
    event_type: str
    subtype: str
    location: str
    basis: str
    notes: str
    fio: str
    personnel_no: str
    format: str
    participants: str

    def values(self) -> tuple[str, ...]:
        return (
            self.start_date,
            self.end_date,
            self.event_type,
            self.subtype,
            self.location,
            self.basis,
            self.notes,
            self.fio,
            self.personnel_no,
            self.format,
            self.participants,
        )


class EventsReport:
    """Shape existing events rows for display/export over a period."""

    def __init__(self, personnel: PersonnelService):
        self.personnel = personnel

    def rows(self, start_date: str, end_date: str) -> tuple[EventsRow, ...]:
        if start_date > end_date:
            raise ValueError(PERIOD_ERROR)

        events = self.personnel.list_events()
        batch_sizes: Counter[str] = Counter(
            str(event["batch_id"]) for event in events if event["batch_id"]
        )

        result: list[EventsRow] = []
        for event in events:
            # Closed-interval overlap with the requested period.
            if str(event["start_date"]) > end_date or str(event["end_date"]) < start_date:
                continue
            batch_id = event["batch_id"]
            is_group = bool(batch_id)
            result.append(
                EventsRow(
                    start_date=format_report_date(event["start_date"]),
                    end_date=format_report_date(event["end_date"]),
                    event_type=_display(event["event_type"]),
                    subtype=_display(event["subtype"]),
                    location=_display(event["location"]),
                    basis=_display(event["basis"]),
                    notes=_display(event["notes"]),
                    fio=_display(event["fio"]),
                    personnel_no=_display(event["personnel_no"]),
                    format=GROUP_LABEL if is_group else SINGLE_LABEL,
                    participants=str(batch_sizes[batch_id] if is_group else 1),
                )
            )
        return tuple(result)

    def table(self, start_date: str, end_date: str) -> ReportTable:
        rows = self.rows(start_date, end_date)
        return ReportTable(events_headers(), tuple(row.values() for row in rows))
