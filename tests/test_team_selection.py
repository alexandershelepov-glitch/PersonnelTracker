from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from database import Database
from services import PersonnelService
from team_selection import SemiAutoTeamService


class FakeDayState:
    def __init__(self, rows):
        self.rows = rows

    def snapshot(self, _target_date: str):
        return SimpleNamespace(rows=tuple(self.rows))


def state_row(person, *, availability="Доступен", source="schedule", status="Работа"):
    return SimpleNamespace(
        employee_id=int(person["id"]),
        fio=str(person["fio"]),
        personnel_no=str(person["personnel_no"]),
        department=str(person["effective_department"] or person["department"] or ""),
        section=str(person["effective_section"] or person["section"] or ""),
        position=str(person["effective_position"] or person["position"] or ""),
        availability=availability,
        source=source,
        status_text=status,
    )


class SemiAutoTeamServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "personnel.db")
        self.service = PersonnelService(self.db)
        self.service.create_demo_data()
        self.people = [self.service.get_employee(int(row["id"])) for row in self.service.list_employees()]
        self.people = [row for row in self.people if row is not None]
        self.target = "2026-09-10"

    def tearDown(self):
        self.tmp.cleanup()

    def batch(self, employee_ids, day: str):
        self.service.create_batch_events(employee_ids, {
            "event_type": "ММ",
            "subtype": "",
            "start_date": day,
            "end_date": day,
            "location": "",
            "basis": "",
            "notes": "",
        })

    def test_fairness_prefers_fewer_and_older_group_assignments(self):
        ids = [int(person["id"]) for person in self.people]
        self.batch([ids[0], ids[1]], "2026-09-01")
        self.batch([ids[0], ids[2]], "2026-09-03")
        rows = [state_row(person) for person in self.people]
        selector = SemiAutoTeamService(self.service, FakeDayState(rows))

        candidates = selector.candidates(self.target, lookback_days=30)
        ranked = [candidate.employee_id for candidate in candidates]

        self.assertEqual(ranked[0], ids[3])  # no recent group assignments
        self.assertLess(ranked.index(ids[1]), ranked.index(ids[2]))  # older last assignment
        self.assertEqual(ranked[-1], ids[0])  # two recent assignments
        self.assertEqual(selector.propose(candidates, 2), ranked[:2])

    def test_existing_event_is_hard_exclusion(self):
        rows = [state_row(person) for person in self.people]
        rows[0] = state_row(self.people[0], availability="Доступен", source="event", status="Вновь принятые")
        selector = SemiAutoTeamService(self.service, FakeDayState(rows))
        candidates = selector.candidates(self.target)
        self.assertNotIn(int(self.people[0]["id"]), [item.employee_id for item in candidates])

    def test_schedule_off_and_needs_check_are_opt_in_and_lower_priority(self):
        rows = [
            state_row(self.people[0]),
            state_row(self.people[1], availability="Требует проверки", source="default", status="Работа / график не задан"),
            state_row(self.people[2], availability="Недоступен", source="schedule", status="Выходной"),
            state_row(self.people[3]),
        ]
        selector = SemiAutoTeamService(self.service, FakeDayState(rows))
        default_ids = [item.employee_id for item in selector.candidates(self.target)]
        self.assertNotIn(int(self.people[1]["id"]), default_ids)
        self.assertNotIn(int(self.people[2]["id"]), default_ids)

        candidates = selector.candidates(
            self.target,
            include_needs_check=True,
            include_schedule_off=True,
        )
        ranks = {item.employee_id: item.schedule_rank for item in candidates}
        self.assertEqual(ranks[int(self.people[0]["id"])], 0)
        self.assertEqual(ranks[int(self.people[1]["id"])], 1)
        self.assertEqual(ranks[int(self.people[2]["id"])], 2)

    def test_weapon_requirement_uses_existing_weapon_records(self):
        armed = self.people[1]
        self.service.add_weapon(int(armed["id"]), "ПМ", "TEST-1")
        rows = [state_row(person) for person in self.people]
        selector = SemiAutoTeamService(self.service, FakeDayState(rows))
        candidates = selector.candidates(self.target, require_weapon=True)
        self.assertEqual([item.employee_id for item in candidates], [int(armed["id"])])


if __name__ == "__main__":
    unittest.main()
