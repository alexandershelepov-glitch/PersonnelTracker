from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from shutil import copyfile
from typing import Any
from uuid import uuid4

try:  # The data layer and its tests remain usable without a GUI installation.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
except ModuleNotFoundError:  # pragma: no cover - used only in headless test environments
    Qt = None
    QImage = None

from config import EVENT_TYPES, UNAVAILABLE_EVENT_TYPES
from database import Database


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
                , COALESCE(u.group_name,'—') AS effective_group
                FROM employees p LEFT JOIN staff_units u ON u.employee_id=p.id WHERE p.id=?""", (employee_id,)).fetchone()

    def save_employee(self, data: dict[str, Any], employee_id: int | None = None) -> int:
        fields = [
            "fio", "personnel_no", "department", "position", "birth_date",
            "factual_address", "registration_address", "phone", "email",
            "employment_date", "schedule_type", "schedule_anchor_date", "employment_status", "section",
        ]
        nullable = {"birth_date", "employment_date", "schedule_anchor_date"}
        values = [data.get(field) or None if field in nullable else data.get(field, "") for field in fields]
        values[fields.index("schedule_type")] = data.get("schedule_type") or "Не задан"
        values[fields.index("employment_status")] = data.get("employment_status") or "Работает"
        values[fields.index("section")] = data.get("section") or "Не указано"
        with self.db.connect() as conn:
            if employee_id:
                assignments = ", ".join(f"{field}=?" for field in fields)
                conn.execute(f"UPDATE employees SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*values, employee_id))
                unit=conn.execute("SELECT id FROM staff_units WHERE employee_id=?",(employee_id,)).fetchone()
                if unit:
                    conn.execute("UPDATE staff_units SET department=?,section=?,position=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(data.get("department", ""),data.get("section") or "Не указано",data.get("position", ""),unit["id"]))
                    if (data.get("employment_status") or "Работает") != "Работает":
                        conn.execute("UPDATE staff_units SET employee_id=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(unit["id"],))
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
        name = f"{uuid4().hex}.jpg"
        target = self.db.photos_dir / name
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
                raise ValueError("Не удалось сохранить уменьшенную фотографию.")
        relative = f"photos/{name}"
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

    def archive_employee(self, employee_id: int, status: str = "Архив") -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE employees SET employment_status=?, archive_date=date('now'), updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, employee_id))

    # ---------- staff structure ----------
    def list_staff_units(self, section: str = "Все", search: str = ""):
        sql = """SELECT u.*, p.fio, p.personnel_no, p.employment_status
                 FROM staff_units u LEFT JOIN employees p ON p.id=u.employee_id WHERE 1=1"""
        args: list[Any] = []
        if section != "Все": sql += " AND u.section=?"; args.append(section)
        if search.strip():
            term=f"%{search.strip()}%"; sql += " AND (u.position LIKE ? OR u.section LIKE ? OR p.fio LIKE ? OR p.personnel_no LIKE ?)"; args += [term]*4
        with self.db.connect() as conn:
            return conn.execute(sql+" ORDER BY CAST(u.unit_number AS INTEGER), u.unit_number",args).fetchall()

    def save_staff_unit(self, data: dict[str, str], unit_id: int | None = None) -> int:
        if not data.get("section") or (data["section"] == "Не указано" and unit_id is None) or not data.get("position", "").strip(): raise ValueError("Для новой штатной единицы укажите отделение и должность.")
        employee_id = int(data["employee_id"]) if data.get("employee_id") else None
        with self.db.connect() as conn:
            if employee_id:
                occupied=conn.execute("SELECT id FROM staff_units WHERE employee_id=? AND id<>?",(employee_id,unit_id or -1)).fetchone()
                if occupied: raise ValueError("Этот работник уже занимает другую штатную единицу.")
            if unit_id:
                conn.execute("UPDATE staff_units SET unit_number=?,department=?,section=?,group_name=?,position=?,employee_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(data["unit_number"].strip(),data.get("department","").strip(),data["section"],data.get("group_name") or None,data["position"].strip(),employee_id,unit_id)); result=unit_id
            else:
                cur=conn.execute("INSERT INTO staff_units(unit_number,department,section,group_name,position,employee_id) VALUES(?,?,?,?,?,?)",(data["unit_number"].strip(),data.get("department","").strip(),data["section"],data.get("group_name") or None,data["position"].strip(),employee_id)); result=int(cur.lastrowid)
            if employee_id: conn.execute("UPDATE employees SET department=?,section=?,position=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(data.get("department","").strip(),data["section"],data["position"].strip(),employee_id))
            return result

    def staff_unit(self, unit_id: int):
        with self.db.connect() as conn: return conn.execute("SELECT * FROM staff_units WHERE id=?",(unit_id,)).fetchone()

    def staff_metrics(self, target_date: str, section: str = "Все") -> dict[str, Any]:
        units=self.list_staff_units(section)
        occupied=[u for u in units if u["employee_id"] and u["employment_status"] == "Работает"]
        employee_sections={int(u["employee_id"]):u["section"] for u in occupied}
        statuses={s.employee_id:s for s in self.daily_statuses(target_date) if s.employee_id in employee_sections}
        absent=[s for s in statuses.values() if s.status in UNAVAILABLE_EVENT_TYPES or s.status=="Выходной"]
        present=[s for s in statuses.values() if s not in absent]
        total={"staff":len(units),"listed":len(occupied),"vacant":len(units)-len(occupied),"absent":len(absent),"present":len(present)}
        by_section={}
        for name in ["Руководство","1 отделение","2 отделение","Не указано"]:
            by_section[name]=self.staff_metrics(target_date,name)["total"] if section=="Все" else {}
        return {"total":total,"absent":absent,"present":present,"employee_sections":employee_sections,"by_section":by_section,"valid":total["listed"]==total["present"]+total["absent"] and total["staff"]==total["listed"]+total["vacant"]}

    def unassigned_active_employees(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT p.* FROM employees p LEFT JOIN staff_units u ON u.employee_id=p.id WHERE p.employment_status='Работает' AND u.id IS NULL ORDER BY p.fio").fetchall()

    def staff_people(self, target_date: str, kind: str, section: str = "Все"):
        metrics=self.staff_metrics(target_date,section)
        if kind not in {"absent","present"}: raise ValueError("Недопустимый тип списка")
        return [{"fio":s.fio,"section":metrics["employee_sections"][s.employee_id],"position":s.position,"reason":s.label,"personnel_no":s.personnel_no} for s in metrics[kind]]

    def weapon_summary(self, employee_id: int) -> str:
        rows=self.list_simple_history("weapons",employee_id)
        return ", ".join(r["weapon_type"] for r in rows) or "—"

    def weapon_text(self, employee_id: int) -> str:
        return "; ".join(f"{r['weapon_type']} №{r['serial_number']}" for r in self.list_simple_history("weapons",employee_id))

    def archived_employees(self, search: str = ""):
        sql="SELECT * FROM employees WHERE employment_status<>'Работает'"; args=[]
        if search.strip(): sql+=" AND (fio LIKE ? OR personnel_no LIKE ?)"; args=[f"%{search.strip()}%"]*2
        with self.db.connect() as conn: return conn.execute(sql+" ORDER BY fio",args).fetchall()

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
            conn.execute("DELETE FROM events WHERE id=?", (event_id,))

    def update_event(self, event_id: int, employee_id: int, data: dict[str, str]) -> None:
        self._validate_event(event_id, employee_id, data)
        with self.db.connect() as conn:
            conn.execute("UPDATE events SET event_type=?, subtype=?, start_date=?, end_date=?, location=?, basis=?, notes=? WHERE id=? AND employee_id=?", (data["event_type"], data.get("subtype", ""), data["start_date"], data["end_date"], data.get("location", ""), data.get("basis", ""), data.get("notes", ""), event_id, employee_id))

    def events_for_employee(self, employee_id: int):
        with self.db.connect() as conn:
            return conn.execute("SELECT * FROM events WHERE employee_id=? ORDER BY start_date DESC, id DESC", (employee_id,)).fetchall()

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
        return {"date": target_date, "authorized": int(self.db.get_setting("authorized_headcount", "0") or 0), "listed": len(statuses), "available": available, "statuses": statuses, "grouped": grouped}

    def render_daily_text(self, target_date: str) -> str:
        m=self.staff_metrics(target_date)["total"]
        return "\n".join([date.fromisoformat(target_date).strftime("%d.%m.%Y"),"",f"По штату - {m['staff']}",f"По списку - {m['listed']}",f"Вакантно - {m['vacant']}",f"Отсутствуют - {m['absent']}",f"На лицо - {m['present']}"])

    def seed_demo_data(self) -> None:
        if self.list_employees(include_archived=True): raise ValueError("Демо-данные можно добавить только в пустую базу")
        self.db.set_setting("authorized_headcount", "5")
        demo = [("Иванов Иван Иванович", "000001", "3 отдел", "инспектор", "1990-05-12", "2020-03-01", "2026-08-24"), ("Петров Пётр Петрович", "000002", "3 отдел", "инспектор", "1988-02-03", "2019-06-15", "2026-08-25"), ("Сидоров Алексей Сергеевич", "000003", "3 отдел", "старший инспектор", "1985-09-21", "2018-11-10", "2026-08-26"), ("Орлов Дмитрий Андреевич", "000004", "3 отдел", "инспектор", "1992-01-19", "2023-04-05", "2026-08-27")]
        ids = [self.save_employee({"fio": fio, "personnel_no": number, "department": dep, "position": pos, "birth_date": birth, "employment_date": hired, "factual_address": "", "registration_address": "", "phone": "", "email": "", "schedule_type": "1/3", "schedule_anchor_date": anchor, "employment_status": "Работает"}) for fio, number, dep, pos, birth, hired, anchor in demo]
        self.add_event({"employee_id": str(ids[1]), "event_type": "Отпуск", "subtype": "очередной", "start_date": "2026-08-24", "end_date": "2026-08-31", "location": "", "basis": "", "notes": "Демо"})
        self.add_event({"employee_id": str(ids[2]), "event_type": "Сдача медкомиссии", "subtype": "", "start_date": "2026-08-25", "end_date": "2026-08-25", "location": "", "basis": "", "notes": "Демо"})
