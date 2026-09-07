"""Semi-automatic team proposal logic for PersonnelTracker v0.8.3-G.

This module contains business/UI-independent ranking only. It does not persist a
team. Existing events remain the source of availability/conflicts, and only
previous batch assignments are counted for the fairness signal so absences such
as vacation or sick leave never increase somebody's "participation" count.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from services import PersonnelService


@dataclass(frozen=True)
class TeamCandidate:
    employee_id: int
    fio: str
    personnel_no: str
    phone: str
    department: str
    section: str
    group_name: str
    position: str
    schedule_type: str
    day_status: str
    availability: str
    schedule_rank: int
    participation_count: int
    last_participation: str
    has_weapon: bool
    reason: str


class SemiAutoTeamService:
    """Build an explainable candidate pool and rank it without persistence."""

    def __init__(self, personnel: PersonnelService, day_state: Any):
        self.personnel = personnel
        self.day_state = day_state

    def participation_stats(self, target_date: str, lookback_days: int) -> dict[int, tuple[int, str]]:
        target = date.fromisoformat(target_date)
        start = (target - timedelta(days=max(1, int(lookback_days)))).isoformat()
        with self.personnel.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT employee_id, COUNT(*) AS participation_count,
                       MAX(start_date) AS last_participation
                FROM events
                WHERE batch_id IS NOT NULL AND batch_id<>''
                  AND start_date>=? AND start_date<?
                GROUP BY employee_id
                """,
                (start, target_date),
            ).fetchall()
        return {
            int(row["employee_id"]): (
                int(row["participation_count"] or 0),
                str(row["last_participation"] or ""),
            )
            for row in rows
        }

    @staticmethod
    def _matches(value: str, expected: str) -> bool:
        return expected == "Все" or value == expected

    def candidates(
        self,
        target_date: str,
        *,
        lookback_days: int = 30,
        department: str = "Все",
        section: str = "Все",
        group_name: str = "Все",
        position: str = "Все",
        schedule_type: str = "Все",
        include_schedule_off: bool = False,
        include_needs_check: bool = False,
        require_weapon: bool = False,
    ) -> list[TeamCandidate]:
        snapshot = self.day_state.snapshot(target_date)
        stats = self.participation_stats(target_date, lookback_days)
        result: list[TeamCandidate] = []

        for row in snapshot.rows:
            # Any existing event on the selected day would collide with the
            # current event-overlap rule, regardless of its semantic category.
            if row.source == "event":
                continue

            details = self.personnel.get_employee(int(row.employee_id))
            if details is None:
                continue

            dep = str(row.department or "")
            sec = str(row.section or "")
            grp = str(details["effective_group"] or details["group_name"] or "—")
            pos = str(row.position or "")
            schedule = str(details["schedule_type"] or "Не задан")
            if not all((
                self._matches(dep, department),
                self._matches(sec, section),
                self._matches(grp, group_name),
                self._matches(pos, position),
                self._matches(schedule, schedule_type),
            )):
                continue

            if row.availability == "Доступен":
                schedule_rank = 0
                schedule_reason = "по графику"
            elif row.availability == "Требует проверки":
                if not include_needs_check:
                    continue
                schedule_rank = 1
                schedule_reason = "график требует проверки"
            else:
                # A schedule-generated day off can be allowed explicitly. An
                # event-generated unavailability was already excluded above.
                if row.source != "schedule" or not include_schedule_off:
                    continue
                schedule_rank = 2
                schedule_reason = "выходной по графику (разрешён)"

            has_weapon = self.personnel.weapon_summary(int(row.employee_id)) != "—"
            if require_weapon and not has_weapon:
                continue

            count, last = stats.get(int(row.employee_id), (0, ""))
            fairness = (
                f"{count} групп. назначений за {int(lookback_days)} дн."
                if count
                else f"нет групп. назначений за {int(lookback_days)} дн."
            )
            if last:
                fairness += f", последнее {date.fromisoformat(last).strftime('%d.%m.%Y')}"
            reason = f"{schedule_reason} • {fairness}"
            if require_weapon:
                reason += " • оружие закреплено"

            result.append(TeamCandidate(
                employee_id=int(row.employee_id),
                fio=str(row.fio or ""),
                personnel_no=str(row.personnel_no or ""),
                phone=str(details["phone"] or ""),
                department=dep,
                section=sec,
                group_name=grp,
                position=pos,
                schedule_type=schedule,
                day_status=str(row.status_text or ""),
                availability=str(row.availability or ""),
                schedule_rank=schedule_rank,
                participation_count=count,
                last_participation=last,
                has_weapon=has_weapon,
                reason=reason,
            ))

        # Fairness: workday first; then fewer recent group assignments; then
        # the person whose last assignment was longer ago (no history first).
        return sorted(
            result,
            key=lambda item: (
                item.schedule_rank,
                item.participation_count,
                item.last_participation or "",
                item.fio.casefold(),
            ),
        )

    @staticmethod
    def propose(candidates: list[TeamCandidate], desired_count: int) -> list[int]:
        count = max(0, int(desired_count))
        return [item.employee_id for item in candidates[:count]]
