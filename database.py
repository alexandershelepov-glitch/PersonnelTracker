from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS employees (
 id INTEGER PRIMARY KEY AUTOINCREMENT, fio TEXT NOT NULL, personnel_no TEXT NOT NULL UNIQUE,
 department TEXT NOT NULL DEFAULT '', position TEXT NOT NULL DEFAULT '', section TEXT NOT NULL DEFAULT 'Не указано',
 birth_date TEXT, factual_address TEXT NOT NULL DEFAULT '', registration_address TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', employment_date TEXT,
 schedule_type TEXT NOT NULL DEFAULT 'Не задан', schedule_anchor_date TEXT, employment_status TEXT NOT NULL DEFAULT 'Работает', archive_date TEXT,
 photo_path TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS staff_units (
 id INTEGER PRIMARY KEY AUTOINCREMENT, unit_number TEXT NOT NULL UNIQUE, department TEXT NOT NULL DEFAULT '',
 section TEXT NOT NULL, group_name TEXT, position TEXT NOT NULL, employee_id INTEGER UNIQUE REFERENCES employees(id) ON DELETE SET NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS medical_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, check_date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS periodic_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, check_date TEXT NOT NULL, result TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS trainings (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, specialty TEXT NOT NULL, training_date TEXT NOT NULL, order_ref TEXT NOT NULL DEFAULT '', certificate TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS weapons (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, weapon_type TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL, assignment_date TEXT, removal_date TEXT, basis TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, event_type TEXT NOT NULL, subtype TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL, end_date TEXT NOT NULL, location TEXT NOT NULL DEFAULT '', basis TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, CHECK(end_date>=start_date));
CREATE INDEX IF NOT EXISTS idx_events_employee_dates ON events(employee_id,start_date,end_date);
CREATE INDEX IF NOT EXISTS idx_events_dates ON events(start_date,end_date);
"""

class Database:
 CURRENT_VERSION=4
 def __init__(self,path:str|Path): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.initialize()
 @property
 def photos_dir(self): p=self.path.parent/'photos'; p.mkdir(parents=True,exist_ok=True); return p
 @contextmanager
 def connect(self)->Iterator[sqlite3.Connection]:
  c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
  try: yield c; c.commit()
  except Exception: c.rollback(); raise
  finally: c.close()
 def initialize(self):
  with self.connect() as c:
   c.executescript(SCHEMA)
   cols={r['name'] for r in c.execute('PRAGMA table_info(employees)')}
   if 'photo_path' not in cols: c.execute('ALTER TABLE employees ADD COLUMN photo_path TEXT')
   if 'section' not in cols: c.execute("ALTER TABLE employees ADD COLUMN section TEXT NOT NULL DEFAULT 'Не указано'")
   unit_cols={r['name'] for r in c.execute('PRAGMA table_info(staff_units)')}
   if 'group_name' not in unit_cols: c.execute('ALTER TABLE staff_units ADD COLUMN group_name TEXT')
   # Safe 0.3 migration: every current worker gets a separate, editable unit.
   for p in c.execute("SELECT id,personnel_no,department,section,position FROM employees WHERE employment_status='Работает'").fetchall():
    c.execute("INSERT OR IGNORE INTO staff_units(unit_number,department,section,position,employee_id) VALUES(?,?,?,?,?)",(f"М-{p['id']}",p['department'],p['section'] or 'Не указано',p['position'] or 'Не указана',p['id']))
   c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('authorized_headcount','0')")
   c.execute("INSERT INTO settings(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(self.CURRENT_VERSION),))
 def get_setting(self,key,default=''):
  with self.connect() as c:
   r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone(); return r['value'] if r else default
 def set_setting(self,key,value):
  with self.connect() as c: c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value))
