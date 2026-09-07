from __future__ import annotations

from datetime import datetime
from typing import Any

from database import Database


REQUIRED_COLUMNS = {
    "id",
    "employee_id",
    "staff_unit_id",
    "employee_fio",
    "employee_personnel_no",
    "unit_number",
    "department",
    "section",
    "group_name",
    "position",
    "start_at",
    "end_at",
    "source",
    "created_at",
}

KNOWN_TRIGGERS = (
    "trg_staff_assignment_insert",
    "trg_staff_assignment_occupant_change",
    "trg_staff_assignment_unit_change",
)

KNOWN_INDEXES = (
    "idx_staff_assignments_employee",
    "idx_staff_assignments_unit",
    "idx_staff_assignments_open_employee",
    "idx_staff_assignments_open_unit",
)


def repair_legacy_assignment_history(db: Database) -> str | None:
    """Move an incompatible pre-v0.8 staff_assignments table aside safely.

    Some development databases may already contain a table with this name but
    with a different set of columns.  SQLite's ``CREATE TABLE IF NOT EXISTS``
    deliberately does not modify such a table, so later v0.8 indexes would fail.

    We never delete that legacy data.  The whole table is renamed to a unique
    ``staff_assignments_legacy_...`` name, known v0.8 trigger/index names are
    released, and the v0.8 tracking start marker is cleared so a truthful new
    baseline can be created from the current staff structure.
    """
    with db.connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='staff_assignments'"
        ).fetchone()
        if not exists:
            return None

        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(staff_assignments)").fetchall()
        }
        if REQUIRED_COLUMNS.issubset(columns):
            return None

        # Remove only names owned by the v0.8 implementation.  The legacy table
        # itself and all of its rows remain preserved.
        for trigger in KNOWN_TRIGGERS:
            connection.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
        for index in KNOWN_INDEXES:
            connection.execute(f'DROP INDEX IF EXISTS "{index}"')

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"staff_assignments_legacy_{stamp}"
        legacy_name = base
        suffix = 1
        while connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (legacy_name,),
        ).fetchone():
            suffix += 1
            legacy_name = f"{base}_{suffix}"

        # The generated name contains only letters, digits and underscores.
        connection.execute(
            f'ALTER TABLE "staff_assignments" RENAME TO "{legacy_name}"'
        )
        connection.execute(
            "DELETE FROM settings WHERE key='history_tracking_started_at'"
        )
        return legacy_name


def install_assignment_history_features(window: Any) -> None:
    """Install v0.8 history with compatibility repair before every ensure call."""
    import assignment_history as feature

    if not getattr(feature, "_legacy_compat_installed", False):
        original_ensure = feature.ensure_assignment_history

        def safe_ensure(db: Database) -> str:
            repair_legacy_assignment_history(db)
            return original_ensure(db)

        # AssignmentHistoryService and the restore wrapper both resolve this
        # module global at runtime, so one wrapper protects startup and restores.
        feature.ensure_assignment_history = safe_ensure
        feature._legacy_compat_installed = True

    repair_legacy_assignment_history(window.db)
    feature.install_assignment_history_features(window)
