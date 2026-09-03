from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from shutil import copyfile
from typing import Any
from uuid import uuid4
import re

try:  # The data layer and its tests remain usable without a GUI installation.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
except ModuleNotFoundError:  # pragma: no cover - used only in headless test environments
    Qt = None
    QImage = None

from config import EVENT_TYPES, UNAVAILABLE_EVENT_TYPES
from database import Database


def calculate_age(birth_date: str | None, on_date: date | None = None) -> int | None:
    """Return full years as of ``on_date``; age is deliberately not persisted."""
    if not birth_date:
        return None
    try:
        born = date.fromisoformat(str(birth_date).strip())
    except (TypeError, ValueError):
        return None
    today = on_date or date.today()
    if born > today:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def format_age(birth_date: str | None, on_date: date | None = None, empty: str = "Не указан") -> str:
    """UI-facing age label. Invalid or empty dates never raise."""
    age = calculate_age(birth_date, on_date)
    return f"{age} лет" if age is not None else empty


def natural_sort_key(value: str | None) -> tuple:
    """Sort 2 before 10 and M-2 before M-10 without coercing legacy IDs to 0."""
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value or ""))


class BatchConflictError(ValueError):
    """Raised when a batch assignment overlaps existing events.

    Carries the full conflict list so the UI can show every clashing
    record without the service deciding what is acceptable."""

    def __init__(self, conflicts: list[dict[str, Any]]):
        super().__init__("Обнаружены пересечения с существующими событиями.")
        self.conflicts = conflicts


@dataclass(frozen=True)
class DailyStatus:
    employee_id: int
    fio: str
    personnel_no: str
    department: str
    position: str
    status: str
    subtype: str = ""
    location: str = ""
    source: str = "schedule"

    @property
    def label(self) -> str:
        return f"{self.status}: {self.subtype}" if self.subtype else self.status


class PersonnelService:
    def __init__(self, db: Database):
        self.db = db

    # ---------- employees and photos ----------
    def list_employees(self, search: str = "", include_archived: bool = False):
        sql = "SELECT * FROM employees WHERE 1=1"
        params: list[Any] = []
        if not include_archived:
            sql += " AND employment_status='Работает'"
        if search.strip():
            term = f"%{search.strip()}%"
            sql += " AND (fio LIKE ? OR personnel_no LIKE ? OR department LIKE ? OR position LIKE ?)"
            params.extend([term] * 4)
        sql += " ORDER BY fio COLLATE NOCASE"
        with self.db.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def get_employee(self, employee_id: int):
        with self.db.connect() as conn:
            return conn.execute("""SELECT p.*, u.id AS staff_unit_id,
                COALESCE(u.department,p.department) AS effective_department,
                COALESCE(u.section,p.section) AS effective_section,
                COALESCE(u.position,p.position) AS effective_position
                , COALESCE(u.group_name,p.group_name,'—') AS effective_group
                FROM employees p LEFT JOIN staff_units u ON u.employee_id=p.id WHERE p.id=?""", (employee_id,)).fetchone()

    def save_employee(self, data: dict[str, Any], employee_id: int | None = None) -> int:
        fields = [
            "fio", "personnel_no", "department", "position", "birth_date",
            "factual_address", "registration_address", "phone", "email",
            "employment_date", "schedule_type", "schedule_anchor_date", "employment_status", "section",
            "group_name", "education", "certificate_number",
        ]
        nullable = {"birth_date", "employment_date", "schedule_anchor_date", "archive_date", "group_name"}
        values = [data.get(field) or None if field in nullable else data.get(field, "") for field in fields]
        values[fields.index("schedule_type")] = data.get("schedule_type") or "Не задан"
        values[fields.index("employment_status")] = data.get("employment_status") or "Работает"
        values[fields.index("section")] = data.get("section") or "Не указано"
        group_name = (data.get("group_name") or "").strip() or None
        values[fields.index("group_name")] = group_name
        with self.db.connect() as conn:
            if employee_id:
                unit = conn.execute("SELECT * FROM staff_units WHERE employee_id=?", (employee_id,)).fetchone()
                # A filled staff unit is the canonical organisation record.  A
                # card edit must not silently move its occupant elsewhere.
                if unit:
                    for field in ("department", "section", "position"):
                        values[fields.index(field)] = unit[field]
                    values[fields.index("group_name")] = unit["group_name"]
                status = values[fields.index("employment_status")]
                assignments = ", ".join(f"{field}=?" for field in fields)
                conn.execute(f"UPDATE employees SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*values, employee_id))
                if status != "Работает":
                    archive_date = data.get("archive_date") or date.today().isoformat()
                    conn.execute("UPDATE employees SET archive_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (archive_date, employee_id))
                    if unit:
                        conn.execute("UPDATE staff_units SET employee_id=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(unit["id"],))
                elif data.get("archive_date") is not None:
                    conn.execute("UPDATE employees SET archive_date=NULL WHERE id=?", (employee_id,))
                return employee_id
            cur = conn.execute(
                f"INSERT INTO employees({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})", values
            )
            return int(cur.lastrowid)

    def photo_file(self, relative_path: str | None) -> Path | None:
        if not relative_path:
            return None
        candidate = (self.db.path.parent / relative_path).resolve()
        photos_root = self.db.photos_dir.resolve()
        return candidate if candidate.is_relative_to(photos_root) else None

    def save_photo(self, employee_id: int, source: str | Path) -> str:
        """Create a compact JPEG in data/photos and persist only its relative path."""
        target = self.db.photos_dir / f"{uuid4().hex}.jpg"
        if QImage is None:
            # The application distribution always installs PySide6.  This
            # fallback is deliberately limited to headless service tests.
            copyfile(source, target)
        else:
            image = QImage(str(source))
            if image.isNull():
                raise ValueError("Не удалось прочитать файл изображения.")
            image = image.scaled(600, 750, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not image.save(str(target), "JPG", 88):
                # Some Qt installations do not expose the JPEG image plugin in
                # headless or restricted environments. PNG keeps the photo
                # usable instead of failing to save a valid image altogether.
                target = target.with_suffix(".png")
                if not image.save(str(target), "PNG"):
                    raise ValueError("Не удалось сохранить уменьшенную фотографию.")
        relative = f"photos/{target.name}"
        old: str | None = None
        with self.db.connect() as conn:
            row = conn.execute("SELECT photo_path FROM employees WHERE id=?", (employee_id,)).fetchone()
            if not row:
                target.unlink(missing_ok=True)
                raise ValueError("Работник не найден.")
            old = row["photo_path"]
            conn.execute("UPDATE employees SET photo_path=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (relative, employee_id))
        old_file = self.photo_file(old)
        if old_file and old_file != target:
            old_file.unlink(missing_ok=True)
        return relative

    def remove_photo(self, employee_id: int) -> None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT photo_path FROM employees WHERE id=?", (employee_id,)).fetchone()
            if not row:
                return
            conn.execute("UPDATE employees SET photo_path=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?", (employee_id,))
        old_file = self.photo_file(row["photo_path"])
        if old_file:
            old_file.unlink(missing_ok=True)

    def archive_employee(self, employee_id: int, status: str = "Архив", archive_date: str | None = None) -> None:
        person = self.get_employee(employee_id)
        if not person:
            raise ValueError("Работник не найден.")
        data = dict(person)
        data.update({"employment_status": status, "archive_date": archive_date or date.today().isoformat()})
        self.save_employee(data, employee_id)

    # ---------- staff structure ----------
    EMPTY_PLACEHOLDER = "—"

    def _staff_row_values(self, row) -> dict[str, str]:
        """Rendered value of every visible SHDS column for one staff unit row.

        Shared by list/filter logic and the filter-value generator so the UI
        can never offer a filter the service cannot evaluate.  Empty values
        use the single EMPTY_PLACEHOLDER consistently."""
        active = bool(row["employee_id"] and row["employment_status"] == "Работает")
        def employee_field(name: str) -> str:
            value = row[name] if active else None
            return str(value) if value else self.EMPTY_PLACEHOLDER
        age = calculate_age(row["birth_date"]) if active else None
        med = periodic = None
        if active:
            med, periodic = self.latest_check_dates(int(row["employee_id"]))
        return {
            "№": str(row["unit_number"] or self.EMPTY_PLACEHOLDER),
            "Отдел": str(row["department"] or self.EMPTY_PLACEHOLDER),
            "Отделение": str(row["section"] or "Не указано"),
            "Группа": str(row["group_name"] or self.EMPTY_PLACEHOLDER),
            "Должность": str(row["position"] or self.EMPTY_PLACEHOLDER),
            "ФИО": str(row["fio"]) if active and row["fio"] else "ВАКАНСИЯ",
            "Таб. №": employee_field("personnel_no"),
            "Дата рождения": employee_field("birth_date"),
            "Возраст": str(age) if age is not None else self.EMPTY_PLACEHOLDER,
            "Телефон": employee_field("phone"),
            "Вооружение": self.weapon_summary(int(row["employee_id"])) if active else self.EMPTY_PLACEHOLDER,
            "Email": employee_field("email"),
            "Дата приёма": employee_field("employment_date"),
            "Последняя МК": med or self.EMPTY_PLACEHOLDER,
            "Последняя ПП": periodic or self.EMPTY_PLACEHOLDER,
            "График": employee_field("schedule_type"),
        }

    def list_staff_units(self, section: str = "Все", search: str = "", filters: dict[str, set[str]] | None = None):
        """Return SHDS units.  Filtering is intentionally applied to rendered
        values so vacancies and computed fields behave exactly like Excel."""
        with self.db.connect() as conn:
            rows = conn.execute("""SELECT u.*, p.fio, p.personnel_no, p.employment_status,
                p.birth_date, p.phone, p.email, p.employment_date, p.schedule_type
                FROM staff_units u LEFT JOIN employees p ON p.id=u.employee_id
                WHERE ?='Все' OR u.section=?""", (section, section)).fetchall()
        needle = search.strip().casefold()
        selected = filters or {}
        result = []
        for row in rows:
            values = self._staff_row_values(row)
            if needle and not any(needle in str(values[key]).casefold() for key in ("№", "ФИО", "Таб. №", "Должность", "Телефон")):
                continue
            if any(values.get(column, "") not in choices for column, choices in selected.items() if choices):
                continue
            result.append(row)
        return sorted(result, key=lambda item: natural_sort_key(item["unit_number"]))

    def staff_filter_values(self, column: str, search: str = "") -> list[str]:
        rows = self.list_staff_units(search=search)
        result: set[str] = {self._staff_row_values(row).get(column, self.EMPTY_PLACEHOLDER) for row in rows}
        return sorted(result, key=natural_sort_key)

    def save_staff_unit(self, data: dict[str, str], unit_id: int | None = None) -> int:
        unit_number = (data.get("unit_number") or "").strip()
        if not unit_number: raise ValueError("Номер штатной единицы обязателен.")
        if not data.get("section") or (data["section"] == "Не указано" and unit_id is None) or not data.get("position", "").strip(): raise ValueError("Для новой штатной единицы укажите отделение и должность.")
        employee_id = int(data["employee_id"]) if data.get("employee_id") else None
        group_name = data.get("group_name") or None
        if data["section"] not in {"1 отделение", "2 отделение"}:
            group_name = None
        with self.db.connect() as conn:
            if unit_id:
                current = conn.execute("SELECT employee_id FROM staff_units WHERE id=?", (unit_id,)).fetchone()
                if not current:
                    raise ValueError("Штатная единица не найдена.")
                occupant = current["employee_id"]
                if occupant and employee_id and int(occupant) != employee_id:
                    raise ValueError("Штатная единица уже занята.")
            if employee_id:
                occupied=conn.execute("SELECT id FROM staff_units WHERE employee_id=? AND id<>?",(employee_id,unit_id or -1)).fetchone()
                if occupied: raise ValueError("Этот работник уже занимает другую штатную единицу.")
            if unit_id:
                conn.execute("UPDATE staff_units SET unit_number=?,department=?,section=?,group_name=?,position=?,employee_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(data["unit_number"].strip(),data.get("department","").strip(),data["section"],group_name,data["position"].strip(),employee_id,unit_id)); result=unit_id
            else:
                cur=conn.execute("INSERT INTO staff_units(unit_number,department,section,group_name,position,employee_id) VALUES(?,?,?,?,?,?)",(data["unit_number"].strip(),data.get("department","").strip(),data["section"],group_name,data["position"].strip(),employee_id)); result=int(cur.lastrowid)
            if employee_id:
                conn.execute("UPDATE employees SET department=?,section=?,group_name=?,position=?, archive_date=NULL, employment_status='Работает', updated_at=CURRENT_TIMESTAMP WHERE id=?",(data.get("department","").strip(),data["section"],group_name,data["position"].strip(),employee_id))
            return result

    def staff_unit(self, unit_id: int):
        with self.db.connect() as conn: return conn.execute("SELECT * FROM staff_units WHERE id=?",(unit_id,)).fetchone()

    def delete_staff_unit(self, unit_id: int) -> None:
        with self.db.connect() as conn:
            unit = conn.execute("SELECT employee_id FROM staff_units WHERE id=?", (unit_id,)).fetchone()
            if not unit:
                raise ValueError("Штатная единица не найдена.")
            if unit["employee_id"]:
                raise ValueError("Штатная единица занята работником. Сначала освободите штатную единицу.")
            conn.execute("DELETE FROM staff_units WHERE id=?", (unit_id,))

    def staff_metrics(self, target_date: str, section: str = "Все") -> dict[str, Any]:
        units=self.list_staff_units(section)
        occupied=[u for u in units if u["employee_id"] and u["employment_status"] == "Работает"]
        employee_sections={int(u["employee_id"]):u["section"] for u in occupied}
        statuses={s.employee_id:s for s in self.daily_statuses(target_date) if s.employee_id in employee_sections}
        absent=[s for s in statuses.values() if s.status in UNAVAILABLE_EVENT_TYPES or s.status=="Выходной"]
        present=[s for s in statuses.values() if s not in absent]
        total={"staff":len(units),"listed":len(occupied),"vacant":len(units)-len(occupied),"absent":len(absent),"present":len(present)}
        by_section={}
        if section == "Все":
            for name in ["Руководство","1 отделение","2 отделение","Не указано"]:
                selected = [unit for unit in units if unit["section"] == name]
                selected_occupied = [unit for unit in selected if unit["employee_id"] and unit["employment_status"] == "Работает"]
                section_statuses = [statuses[int(unit["employee_id"])] for unit in selected_occupied if int(unit["employee_id"]) in statuses]
                section_absent = [item for item in section_statuses if item.status in UNAVAILABLE_EVENT_TYPES or item.status == "Выходной"]
                by_section[name] = {"staff": len(selected), "listed": len(selected_occupied), "vacant": len(selected) - len(selected_occupied), "absent": len(section_absent), "present": len(section_statuses) - len(section_absent)}
        return {"total":total,"absent":absent,"present":present,"employee_sections":employee_sections,"by_section":by_section,"valid":total["listed"]==total["present"]+total["absent"] and total["staff"]==total["listed"]+total["vacant"]}

    def unassigned_active_employees(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT p.* FROM employees p LEFT JOIN staff_units u ON u.employee_id=p.id WHERE p.employment_status='Работает' AND u.id IS NULL ORDER BY p.fio").fetchall()

    def vacant_staff_units(self):
        return [unit for unit in self.list_staff_units() if not unit["employee_id"]]

    def unique_field_values(self, field: str) -> list[str]:
        """Distinct already-used values for personnel-card autocompletion."""
        columns = {"position", "department", "section", "group_name"}
        if field not in columns:
            raise ValueError("Недопустимое поле подсказки")
        seen: dict[str, str] = {}
        with self.db.connect() as conn:
            for table in ("employees", "staff_units"):
                for row in conn.execute(f"SELECT DISTINCT {field} AS value FROM {table}"):
                    raw = (row["value"] or "").strip()
                    if not raw or raw == "—":
                        continue
                    key = raw.casefold()
                    if key not in seen:
                        seen[key] = raw
        return sorted(seen.values(), key=natural_sort_key)

    def assign_employee_to_unit(self, employee_id: int, unit_id: int) -> int:
        person = self.get_employee(employee_id)
        if not person:
            raise ValueError("Работник не найден.")
        if person["employment_status"] != "Работает":
            raise ValueError("Назначить на штатную единицу можно только действующего работника.")
        unit = self.staff_unit(unit_id)
        if not unit:
            raise ValueError("Штатная единица не найдена.")
        if unit["employee_id"] and int(unit["employee_id"]) != int(employee_id):
            raise ValueError("Штатная единица уже занята.")
        return self.save_staff_unit({
            "unit_number": unit["unit_number"],
            "department": unit["department"] or "",
            "section": unit["section"],
            "group_name": unit["group_name"] or "",
            "position": unit["position"],
            "employee_id": employee_id,
        }, unit_id)

    def assignment_status_text(self, employee) -> str:
        if not employee:
            return "Не назначен на штатную единицу"
        status = employee["employment_status"] or "Работает"
        if status != "Работает":
            when = employee["archive_date"]
            return f"{status} с {when}" if when else status
        if not employee["staff_unit_id"]:
            return "Не назначен на штатную единицу"
        unit = self.staff_unit(int(employee["staff_unit_id"]))
        if not unit:
            return "Не назначен на штатную единицу"
        details = [part for part in (unit["position"], unit["section"]) if part]
        suffix = f" ({', '.join(details)})" if details else ""
        return f"Назначен на штатную единицу № {unit['unit_number']}{suffix}"

    def staff_people(self, target_date: str, kind: str, section: str = "Все"):
        metrics=self.staff_metrics(target_date,section)
        if kind not in {"absent","present"}: raise ValueError("Недопустимый тип списка")
        return [{"fio":s.fio,"section":metrics["employee_sections"][s.employee_id],"position":s.position,"reason":s.label,"personnel_no":s.personnel_no} for s in metrics[kind]]

    def weapon_summary(self, employee_id: int) -> str:
        rows=reversed(self.list_simple_history("weapons",employee_id))
        return ", ".join(r["weapon_type"] for r in rows) or "—"

    def weapon_text(self, employee_id: int) -> str:
        return "; ".join(f"{r['weapon_type']} №{r['serial_number']}" for r in reversed(self.list_simple_history("weapons",employee_id)))

    def archived_employees(self, search: str = ""):
        sql="SELECT * FROM employees WHERE employment_status<>'Работает'"; args=[]
        if search.strip(): sql+=" AND (fio LIKE ? OR personnel_no LIKE ?)"; args=[f"%{search.strip()}%"]*2
        with self.db.connect() as conn: return conn.execute(sql+" ORDER BY archive_date DESC, fio",args).fetchall()

    def latest_check_dates(self, employee_id: int) -> tuple[str | None, str | None]:
        with self.db.connect() as conn:
            med = conn.execute("SELECT MAX(check_date) AS d FROM medical_checks WHERE employee_id=?", (employee_id,)).fetchone()["d"]
            periodic = conn.execute("SELECT MAX(check_date) AS d FROM periodic_checks WHERE employee_id=?", (employee_id,)).fetchone()["d"]
        return med, periodic

    # ---------- histories ----------
    def list_simple_history(self, table: str, employee_id: int):
        allowed = {"medical_checks", "periodic_checks", "trainings", "weapons"}
        if table not in allowed:
            raise ValueError("Недопустимая таблица")
        order_col = {"medical_checks": "check_date", "periodic_checks": "check_date", "trainings": "training_date", "weapons": "id"}[table]
        with self.db.connect() as conn:
            return conn.execute(f"SELECT * FROM {table} WHERE employee_id=? ORDER BY {order_col} DESC, id DESC", (employee_id,)).fetchall()

    def get_history_record(self, table: str, record_id: int, employee_id: int):
        if table not in {"medical_checks", "periodic_checks", "trainings", "weapons"}:
            raise ValueError("Недопустимая таблица")
        with self.db.connect() as conn:
            return conn.execute(f"SELECT * FROM {table} WHERE id=? AND employee_id=?", (record_id, employee_id)).fetchone()

    def update_history_record(self, table: str, record_id: int, employee_id: int, data: dict[str, Any]) -> None:
        fields_by_table = {
            "medical_checks": ("check_date", "notes"),
            "periodic_checks": ("check_date", "result", "notes"),
            "trainings": ("specialty", "training_date", "order_ref", "certificate", "notes"),
        }
        if table == "weapons":
            self.update_weapon(record_id, employee_id, data.get("weapon_name", data.get("weapon_type", "")), data.get("serial_number", ""))
            return
        fields = fields_by_table.get(table)
        if not fields:
            raise ValueError("Недопустимая таблица")
        values = [data.get(field, "") for field in fields]
        with self.db.connect() as conn:
            conn.execute(f"UPDATE {table} SET {', '.join(f'{field}=?' for field in fields)} WHERE id=? AND employee_id=?", (*values, record_id, employee_id))

    def delete_history_record(self, table: str, record_id: int, employee_id: int) -> None:
        if table not in {"medical_checks", "periodic_checks", "trainings", "weapons"}:
            raise ValueError("Недопустимая таблица")
        with self.db.connect() as conn:
            conn.execute(f"DELETE FROM {table} WHERE id=? AND employee_id=?", (record_id, employee_id))

    def add_medical_check(self, employee_id: int, check_date: str, notes: str = "") -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO medical_checks(employee_id, check_date, notes) VALUES (?, ?, ?)", (employee_id, check_date, notes))

    def add_periodic_check(self, employee_id: int, check_date: str, result: str = "", notes: str = "") -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO periodic_checks(employee_id, check_date, result, notes) VALUES (?, ?, ?, ?)", (employee_id, check_date, result, notes))

    def add_training(self, employee_id: int, specialty: str, training_date: str, order_ref: str, certificate: str, notes: str = "") -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO trainings(employee_id, specialty, training_date, order_ref, certificate, notes) VALUES (?, ?, ?, ?, ?, ?)", (employee_id, specialty, training_date, order_ref, certificate, notes))

    def add_weapon(self, employee_id: int, weapon_name: str, serial_number: str) -> int:
        if not weapon_name.strip() or not serial_number.strip(): raise ValueError("Укажите наименование оружия и номер.")
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO weapons(employee_id, weapon_type, serial_number) VALUES (?, ?, ?)", (employee_id, weapon_name, serial_number))
            return int(cur.lastrowid)

    def update_weapon(self, record_id: int, employee_id: int, weapon_name: str, serial_number: str) -> None:
        if not weapon_name.strip() or not serial_number.strip(): raise ValueError("Укажите наименование оружия и номер.")
        with self.db.connect() as conn:
            # Reset hidden legacy fields for records edited in v0.3.  Existing,
            # untouched records retain all historical values in the database.
            conn.execute("UPDATE weapons SET weapon_type=?, serial_number=?, model='', assignment_date=NULL, removal_date=NULL, basis='' WHERE id=? AND employee_id=?", (weapon_name, serial_number, record_id, employee_id))

    # ---------- events ----------
    def list_events(self, search: str = ""):
        sql = "SELECT e.*, p.fio, p.personnel_no FROM events e JOIN employees p ON p.id=e.employee_id WHERE 1=1"
        params: list[Any] = []
        if search.strip():
            term = f"%{search.strip()}%"
            sql += " AND (p.fio LIKE ? OR p.personnel_no LIKE ? OR e.event_type LIKE ? OR e.subtype LIKE ?)"
            params.extend([term] * 4)
        with self.db.connect() as conn:
            return conn.execute(sql + " ORDER BY e.start_date DESC, p.fio", params).fetchall()

    def get_event(self, event_id: int):
        with self.db.connect() as conn:
            return conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()

    def _validate_event(self, event_id: int | None, employee_id: int, data: dict[str, str]) -> None:
        start, end = data["start_date"], data["end_date"]
        if end < start:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        with self.db.connect() as conn:
            sql = "SELECT id, event_type, subtype FROM events WHERE employee_id=? AND start_date <= ? AND end_date >= ?"
            args: list[Any] = [employee_id, end, start]
            if event_id is not None:
                sql += " AND id<>?"; args.append(event_id)
            overlap = conn.execute(sql + " LIMIT 1", args).fetchone()
            if overlap:
                existing = overlap["event_type"] + (f" / {overlap['subtype']}" if overlap["subtype"] else "")
                raise ValueError(f"На этот период уже есть событие: {existing}. Сначала измените существующую запись.")

    def add_event(self, data: dict[str, str]) -> int:
        employee_id = int(data["employee_id"]); self._validate_event(None, employee_id, data)
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO events(employee_id, event_type, subtype, start_date, end_date, location, basis, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (employee_id, data["event_type"], data.get("subtype", ""), data["start_date"], data["end_date"], data.get("location", ""), data.get("basis", ""), data.get("notes", "")))
            return int(cur.lastrowid)

    def delete_event(self, event_id: int) -> None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT batch_id FROM events WHERE id=?", (event_id,)).fetchone()
            if row and row["batch_id"]:
                raise ValueError("Запись входит в групповое назначение. Удалить её можно только вместе со всей группой.")
            conn.execute("DELETE FROM events WHERE id=?", (event_id,))

    def update_event(self, event_id: int, employee_id: int, data: dict[str, str]) -> None:
        existing = self.get_event(event_id)
        if not existing:
            raise ValueError("Событие не найдено.")
        if existing["batch_id"]:
            raise ValueError("Запись входит в групповое назначение. Изменить её можно только вместе со всей группой.")
        if int(existing["employee_id"]) != employee_id:
            raise ValueError("Нельзя изменить работника у существующего события. Удалите запись и создайте новую.")
        self._validate_event(event_id, employee_id, data)
        with self.db.connect() as conn:
            conn.execute("UPDATE events SET event_type=?, subtype=?, start_date=?, end_date=?, location=?, basis=?, notes=? WHERE id=? AND employee_id=?", (data["event_type"], data.get("subtype", ""), data["start_date"], data["end_date"], data.get("location", ""), data.get("basis", ""), data.get("notes", ""), event_id, employee_id))

    def events_for_employee(self, employee_id: int):
        with self.db.connect() as conn:
            return conn.execute("SELECT * FROM events WHERE employee_id=? ORDER BY start_date DESC, id DESC", (employee_id,)).fetchall()

    # ---------- batch (group) event assignments ----------
    def find_event_conflicts(self, employee_ids: list[int], start_date: str, end_date: str,
                             exclude_batch_id: str | None = None) -> list[dict[str, Any]]:
        """Every overlap of the period with existing events of the employees.

        Reuses the single-event rule: any intersection of closed intervals is
        a conflict.  ``exclude_batch_id`` keeps a batch from conflicting with
        itself when the whole group is edited."""
        conflicts: list[dict[str, Any]] = []
        with self.db.connect() as conn:
            for employee_id in employee_ids:
                sql = """SELECT e.*, p.fio FROM events e JOIN employees p ON p.id=e.employee_id
                         WHERE e.employee_id=? AND e.start_date <= ? AND e.end_date >= ?"""
                args: list[Any] = [int(employee_id), end_date, start_date]
                if exclude_batch_id is not None:
                    sql += " AND (e.batch_id IS NULL OR e.batch_id<>?)"
                    args.append(exclude_batch_id)
                for row in conn.execute(sql + " ORDER BY e.start_date, e.id", args).fetchall():
                    conflicts.append({
                        "employee_id": int(employee_id), "fio": row["fio"], "event_id": row["id"],
                        "event_type": row["event_type"], "subtype": row["subtype"],
                        "start_date": row["start_date"], "end_date": row["end_date"],
                        "notes": row["notes"],
                    })
        return conflicts

    def create_batch_events(self, employee_ids: list[int], data: dict[str, str]) -> str:
        """Create one ordinary event per employee in a single transaction.

        All-or-nothing: if any selected employee has a conflicting event,
        nothing is created.  Every record gets the same fresh UUID batch_id."""
        unique_ids = [int(value) for value in dict.fromkeys(employee_ids)]
        if len(unique_ids) < 2:
            raise ValueError("Для группового назначения выберите не менее двух работников.")
        if data["end_date"] < data["start_date"]:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        with self.db.connect() as conn:
            placeholders = ",".join("?" for _ in unique_ids)
            found = conn.execute(f"SELECT COUNT(*) AS n FROM employees WHERE id IN ({placeholders})", unique_ids).fetchone()["n"]
            if found != len(unique_ids):
                raise ValueError("В выборке есть несуществующие работники.")
        conflicts = self.find_event_conflicts(unique_ids, data["start_date"], data["end_date"])
        if conflicts:
            raise BatchConflictError(conflicts)
        batch_id = uuid4().hex
        with self.db.connect() as conn:
            for employee_id in unique_ids:
                conn.execute(
                    "INSERT INTO events(employee_id, event_type, subtype, start_date, end_date, location, basis, notes, batch_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (employee_id, data["event_type"], data.get("subtype", ""), data["start_date"], data["end_date"],
                     data.get("location", ""), data.get("basis", ""), data.get("notes", ""), batch_id))
        return batch_id

    def list_batch_events(self, batch_id: str):
        with self.db.connect() as conn:
            return conn.execute("""SELECT e.*, p.fio, p.personnel_no, p.position, p.department, p.section
                FROM events e JOIN employees p ON p.id=e.employee_id
                WHERE e.batch_id=? ORDER BY p.fio COLLATE NOCASE""", (batch_id,)).fetchall()

    def update_batch_events(self, batch_id: str, data: dict[str, str]) -> None:
        """Update shared fields of the whole batch in one transaction.

        The group composition never changes here; the batch is excluded from
        its own conflict check so it cannot conflict with itself."""
        events = self.list_batch_events(batch_id)
        if not events:
            raise ValueError("Группа не найдена.")
        if data["end_date"] < data["start_date"]:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        employee_ids = [int(event["employee_id"]) for event in events]
        conflicts = self.find_event_conflicts(employee_ids, data["start_date"], data["end_date"], exclude_batch_id=batch_id)
        if conflicts:
            raise BatchConflictError(conflicts)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE events SET event_type=?, subtype=?, start_date=?, end_date=?, location=?, basis=?, notes=? WHERE batch_id=?",
                (data["event_type"], data.get("subtype", ""), data["start_date"], data["end_date"],
                 data.get("location", ""), data.get("basis", ""), data.get("notes", ""), batch_id))

    def delete_batch_events(self, batch_id: str) -> int:
        """Delete every record of the batch in one transaction."""
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM events WHERE batch_id=?", (batch_id,))
            return int(cursor.rowcount)

    # ---------- calculation: unchanged from 0.2 ----------
    @staticmethod
    def is_workday_13(target: date, anchor: date) -> bool:
        return (target - anchor).days % 4 == 0

    def daily_statuses(self, target_date: str) -> list[DailyStatus]:
        target = date.fromisoformat(target_date)
        employees = self.list_employees(include_archived=False)
        with self.db.connect() as conn:
            event_rows = conn.execute("SELECT * FROM events WHERE start_date <= ? AND end_date >= ? ORDER BY id DESC", (target_date, target_date)).fetchall()
        by_employee = {int(row["employee_id"]): row for row in event_rows}
        result: list[DailyStatus] = []
        for person in employees:
            event = by_employee.get(int(person["id"]))
            if event:
                result.append(DailyStatus(int(person["id"]), person["fio"], person["personnel_no"], person["department"], person["position"], event["event_type"], event["subtype"], event["location"], "event")); continue
            if person["schedule_type"] == "1/3" and person["schedule_anchor_date"]:
                status = "Работа" if self.is_workday_13(target, date.fromisoformat(person["schedule_anchor_date"])) else "Выходной"; source = "schedule"
            else:
                status, source = "Работа / график не задан", "default"
            result.append(DailyStatus(int(person["id"]), person["fio"], person["personnel_no"], person["department"], person["position"], status, source=source))
        return result

    def daily_summary(self, target_date: str) -> dict[str, Any]:
        statuses = self.daily_statuses(target_date); grouped: dict[tuple[str, str], list[DailyStatus]] = defaultdict(list)
        for status in statuses: grouped[(status.status, status.subtype)].append(status)
        available = [status for status in statuses if status.status not in UNAVAILABLE_EVENT_TYPES and status.status != "Выходной"]
        return {"date": target_date, "listed": len(statuses), "available": available, "statuses": statuses, "grouped": grouped}

    def staff_state_on_date(self, target_date: str) -> list[dict[str, str]]:
        """The date view reuses the sole daily-status calculation."""
        units = self.list_staff_units()
        statuses = {item.employee_id: item for item in self.daily_statuses(target_date)}
        rows: list[dict[str, str]] = []
        for unit in units:
            if not unit["employee_id"] or unit["employment_status"] != "Работает":
                continue
            status = statuses.get(int(unit["employee_id"]))
            if not status:
                continue
            absent = status.status in UNAVAILABLE_EVENT_TYPES or status.status == "Выходной"
            rows.append({
                "unit_number": unit["unit_number"], "fio": unit["fio"], "section": unit["section"],
                "group": unit["group_name"] or "—", "position": unit["position"],
                "state": "Отсутствует" if absent else "На лицо",
                "reason": status.label if absent else "—",
            })
        return rows

    def render_daily_text(self, target_date: str) -> str:
        m=self.staff_metrics(target_date)["total"]
        return "\n".join([date.fromisoformat(target_date).strftime("%d.%m.%Y"),"",f"По штату - {m['staff']}",f"По списку - {m['listed']}",f"Вакантно - {m['vacant']}",f"Отсутствуют - {m['absent']}",f"На лицо - {m['present']}"])

    def create_demo_data(self) -> dict[str, int]:
        """Create the complete demo set only in an empty database.

        The records and their staff units are inserted in one transaction, so a
        failed demo setup cannot leave partially visible test workers behind.
        """
        if self.list_employees(include_archived=True):
            raise ValueError("Демо-данные можно добавить только в пустую базу")
        demo = [
            ("Д-1", "Иванов Иван Иванович", "000001", "1 отделение", "1 группа", "инспектор", "1990-05-12", "2020-03-01", "2026-08-24"),
            ("Д-2", "Петров Пётр Петрович", "000002", "1 отделение", "1 группа", "инспектор", "1988-02-03", "2019-06-15", "2026-08-25"),
            ("Д-3", "Сидоров Алексей Сергеевич", "000003", "2 отделение", "2 группа", "старший инспектор", "1985-09-21", "2018-11-10", "2026-08-26"),
            ("Д-4", "Орлов Дмитрий Андреевич", "000004", "2 отделение", "2 группа", "инспектор", "1992-01-19", "2023-04-05", "2026-08-27"),
        ]
        employee_ids: list[int] = []
        with self.db.connect() as conn:
            for unit_number, fio, number, section, group_name, position, birth, hired, anchor in demo:
                cur = conn.execute(
                    """INSERT INTO employees
                       (fio, personnel_no, department, position, birth_date, factual_address,
                        registration_address, phone, email, employment_date, schedule_type,
                        schedule_anchor_date, employment_status, section, group_name)
                       VALUES (?, ?, '3 отдел', ?, ?, '', '', '', '', ?, '1/3', ?, 'Работает', ?, ?)""",
                    (fio, number, position, birth, hired, anchor, section, group_name),
                )
                employee_id = int(cur.lastrowid)
                employee_ids.append(employee_id)
                conn.execute(
                    """INSERT INTO staff_units(unit_number, department, section, group_name, position, employee_id)
                       VALUES (?, '3 отдел', ?, ?, ?, ?)""",
                    (unit_number, section, group_name, position, employee_id),
                )
            conn.execute(
                """INSERT INTO events(employee_id, event_type, subtype, start_date, end_date, location, basis, notes)
                   VALUES (?, 'Отпуск', 'очередной', '2026-08-24', '2026-08-31', '', '', 'Демо')""",
                (employee_ids[1],),
            )
            conn.execute(
                """INSERT INTO events(employee_id, event_type, subtype, start_date, end_date, location, basis, notes)
                   VALUES (?, 'Сдача медкомиссии', '', '2026-08-25', '2026-08-25', '', '', 'Демо')""",
                (employee_ids[2],),
            )
        return {"employees": len(employee_ids), "staff_units": len(employee_ids), "events": 2}

    def seed_demo_data(self) -> dict[str, int]:
        """Compatibility alias for older callers."""
        return self.create_demo_data()
