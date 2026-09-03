from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from backup import BackupError
from backup_local import LocalBackupManager
from database import Database
from services import PersonnelService


class LocalBackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / "app" / "data"
        self.db = Database(self.data_dir / "personnel.db")
        self.service = PersonnelService(self.db)
        self.service.save_employee({
            "fio": "Тестов Тест Тестович",
            "personnel_no": "TEST-001",
            "department": "3 отдел",
            "section": "1 отделение",
            "group_name": "1 группа",
            "position": "инспектор",
            "birth_date": "1990-01-01",
            "factual_address": "",
            "registration_address": "",
            "phone": "90000000000",
            "email": "",
            "employment_date": "2020-01-01",
            "schedule_type": "5/2",
            "schedule_anchor_date": None,
            "employment_status": "Работает",
        })
        self.manager = LocalBackupManager(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_directory_remains_inside_data_until_user_changes_it(self):
        self.assertEqual(self.manager.backups_dir, (self.data_dir / "backups").resolve())
        self.assertEqual(self.db.get_setting(self.manager.SETTING_KEY, ""), "")

    def test_selected_directory_is_persisted_and_used_for_new_backups(self):
        custom = self.root / "PersonnelTracker Backups"
        selected = self.manager.set_backups_dir(custom)
        self.assertEqual(selected, custom.resolve())

        recreated = LocalBackupManager(self.db)
        self.assertEqual(recreated.backups_dir, custom.resolve())
        backup = recreated.create_backup(kind="manual")
        self.assertEqual(backup.parent, custom.resolve())
        self.assertTrue(backup.exists())

    def test_automatic_backup_uses_selected_directory(self):
        custom = self.root / "offline-backups"
        self.manager.set_backups_dir(custom)
        created = self.manager.create_auto_backup_if_due(datetime(2026, 9, 3, 8, 0, 0))
        self.assertIsNotNone(created)
        self.assertEqual(created.parent, custom.resolve())

    def test_invalid_new_location_does_not_replace_previous_setting(self):
        valid = self.root / "valid-backups"
        self.manager.set_backups_dir(valid)
        invalid = self.root / "not-a-directory"
        invalid.write_text("file", encoding="utf-8")

        with self.assertRaises(BackupError):
            self.manager.set_backups_dir(invalid)

        self.assertEqual(self.manager.configured_backups_dir, valid.resolve())

    def test_safety_backup_before_restore_uses_selected_directory(self):
        custom = self.root / "safety-backups"
        self.manager.set_backups_dir(custom)
        original = self.manager.create_backup(kind="manual")

        person = dict(self.service.list_employees()[0])
        person["fio"] = "Изменённый Тест"
        self.service.save_employee(person, int(person["id"]))

        result = self.manager.restore_backup(original)
        self.assertEqual(result.safety_backup.parent, custom.resolve())
        self.assertTrue(result.safety_backup.exists())
        self.assertIn("before-restore", result.safety_backup.name)


if __name__ == "__main__":
    unittest.main()
