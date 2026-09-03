from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from backup import BackupError, BackupManager
from database import Database
from services import PersonnelService


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.db = Database(self.data_dir / "personnel.db")
        self.service = PersonnelService(self.db)
        self.employee_id = self.service.save_employee({
            "fio": "Иванов Иван Иванович",
            "personnel_no": "1001",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "birth_date": "1990-01-01",
            "factual_address": "",
            "registration_address": "",
            "phone": "89000000000",
            "email": "",
            "employment_date": "2020-01-01",
            "schedule_type": "5/2",
            "schedule_anchor_date": None,
            "employment_status": "Работает",
        })
        photo = self.db.photos_dir / "employee.jpg"
        photo.write_bytes(b"test-photo")
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE employees SET photo_path='photos/employee.jpg' WHERE id=?",
                (self.employee_id,),
            )
        self.manager = BackupManager(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_contains_database_manifest_and_photos(self):
        target = self.manager.create_backup(kind="manual")
        self.assertTrue(target.exists())
        inspection = self.manager.inspect_backup(target)
        self.assertEqual(inspection.schema_version, self.db.CURRENT_VERSION)
        self.assertEqual(inspection.photo_count, 1)
        with zipfile.ZipFile(target) as archive:
            self.assertIn("manifest.json", archive.namelist())
            self.assertIn("database/personnel.db", archive.namelist())
            self.assertIn("photos/employee.jpg", archive.namelist())

    def test_restore_returns_database_and_photos_to_snapshot(self):
        backup = self.manager.create_backup(kind="manual")

        person = dict(self.service.get_employee(self.employee_id))
        person["fio"] = "Изменённый Работник"
        self.service.save_employee(person, self.employee_id)
        (self.db.photos_dir / "employee.jpg").write_bytes(b"changed-photo")
        (self.db.photos_dir / "extra.jpg").write_bytes(b"extra")

        result = self.manager.restore_backup(backup)

        restored = self.service.get_employee(self.employee_id)
        self.assertEqual(restored["fio"], "Иванов Иван Иванович")
        self.assertEqual((self.db.photos_dir / "employee.jpg").read_bytes(), b"test-photo")
        self.assertFalse((self.db.photos_dir / "extra.jpg").exists())
        self.assertTrue(result.safety_backup.exists())
        self.assertIn("before-restore", result.safety_backup.name)

    def test_invalid_zip_is_rejected_without_touching_live_database(self):
        bad = self.data_dir / "broken.zip"
        bad.write_bytes(b"not-a-zip")
        before = self.service.get_employee(self.employee_id)["fio"]
        with self.assertRaises(BackupError):
            self.manager.restore_backup(bad)
        after = self.service.get_employee(self.employee_id)["fio"]
        self.assertEqual(after, before)

    def test_zip_path_traversal_is_rejected(self):
        malicious = self.data_dir / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../outside.txt", "unsafe")
            archive.writestr("manifest.json", "{}")
            archive.writestr("database/personnel.db", b"not-used")
        with self.assertRaises(BackupError):
            self.manager.inspect_backup(malicious)
        self.assertFalse((self.data_dir.parent / "outside.txt").exists())

    def test_automatic_backup_is_created_only_once_per_day(self):
        moment = datetime(2026, 9, 3, 8, 30, 0)
        first = self.manager.create_auto_backup_if_due(moment)
        second = self.manager.create_auto_backup_if_due(moment.replace(hour=18))
        self.assertIsNotNone(first)
        self.assertTrue(first.exists())
        self.assertIsNone(second)

    def test_automatic_backup_retention_keeps_seven_newest(self):
        for day in range(1, 10):
            self.manager.create_auto_backup_if_due(datetime(2026, 8, day, 8, 0, 0))
        backups = list(self.manager.backups_dir.glob("PersonnelTracker-auto-*.zip"))
        self.assertEqual(len(backups), self.manager.AUTO_KEEP)


if __name__ == "__main__":
    unittest.main()
