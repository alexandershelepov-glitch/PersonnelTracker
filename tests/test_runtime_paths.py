from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import runtime_paths
from config import DB_FILENAME
from database import Database


class RuntimePathsTests(unittest.TestCase):
    def test_source_run_keeps_repository_local_data_directory(self):
        with patch.object(runtime_paths, "is_frozen", return_value=False):
            expected = Path(runtime_paths.__file__).resolve().parent / "data"
            self.assertEqual(runtime_paths.data_dir(), expected)
            self.assertEqual(runtime_paths.database_path(), (expected / DB_FILENAME).resolve())

    def test_frozen_macos_uses_application_support(self):
        fake_home = Path("/Users/tester")
        with (
            patch.object(runtime_paths, "is_frozen", return_value=True),
            patch.object(runtime_paths.sys, "platform", "darwin"),
            patch.object(runtime_paths.Path, "home", return_value=fake_home),
        ):
            expected = fake_home / "Library" / "Application Support" / "PersonnelTracker" / "data"
            self.assertEqual(runtime_paths.data_dir(), expected)
            self.assertEqual(runtime_paths.database_path(), (expected / DB_FILENAME).resolve())

    def test_frozen_windows_uses_localappdata(self):
        local_appdata = Path("/tmp/FakeUser/AppData/Local")
        with (
            patch.object(runtime_paths, "is_frozen", return_value=True),
            patch.object(runtime_paths.sys, "platform", "win32"),
            patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}),
        ):
            expected = local_appdata / "PersonnelTracker" / "data"
            self.assertEqual(runtime_paths.data_dir(), expected)
            self.assertEqual(runtime_paths.database_path(), (expected / DB_FILENAME).resolve())

    def test_frozen_windows_without_localappdata_uses_predictable_fallback(self):
        fake_home = Path("/tmp/FakeHome")
        env_without_localappdata = {key: value for key, value in os.environ.items() if key != "LOCALAPPDATA"}
        with (
            patch.object(runtime_paths, "is_frozen", return_value=True),
            patch.object(runtime_paths.sys, "platform", "win32"),
            patch.object(runtime_paths.Path, "home", return_value=fake_home),
            patch.dict(os.environ, env_without_localappdata, clear=True),
        ):
            expected = fake_home / "AppData" / "Local" / "PersonnelTracker" / "data"
            self.assertEqual(runtime_paths.data_dir(), expected)
            self.assertEqual(runtime_paths.database_path(), (expected / DB_FILENAME).resolve())

    def test_macos_frozen_ignores_windows_environment_variable(self):
        fake_home = Path("/Users/tester")
        with (
            patch.object(runtime_paths, "is_frozen", return_value=True),
            patch.object(runtime_paths.sys, "platform", "darwin"),
            patch.object(runtime_paths.Path, "home", return_value=fake_home),
            patch.dict(os.environ, {"LOCALAPPDATA": "/tmp/FakeUser/AppData/Local"}),
        ):
            expected = fake_home / "Library" / "Application Support" / "PersonnelTracker" / "data"
            self.assertEqual(runtime_paths.data_dir(), expected)

    def test_windows_runtime_path_is_not_used_by_source_runs(self):
        with (
            patch.object(runtime_paths, "is_frozen", return_value=False),
            patch.object(runtime_paths.sys, "platform", "win32"),
            patch.dict(os.environ, {"LOCALAPPDATA": "/tmp/FakeUser/AppData/Local"}),
        ):
            expected = Path(runtime_paths.__file__).resolve().parent / "data"
            self.assertEqual(runtime_paths.data_dir(), expected)

    def test_missing_directories_are_created_for_the_database_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "PersonnelTracker" / "data"
            self.assertFalse(nested.exists())
            Database(nested / DB_FILENAME)
            self.assertTrue((nested / DB_FILENAME).exists())

    def test_app_reexports_runtime_path_helpers(self):
        self.assertIs(app.data_dir, runtime_paths.data_dir)
        self.assertIs(app.database_path, runtime_paths.database_path)

    def test_non_macos_frozen_falls_back_to_source_layout_for_now(self):
        with (
            patch.object(runtime_paths, "is_frozen", return_value=True),
            patch.object(runtime_paths.sys, "platform", "linux"),
        ):
            expected = Path(runtime_paths.__file__).resolve().parent / "data"
            self.assertEqual(runtime_paths.data_dir(), expected)


if __name__ == "__main__":
    unittest.main()
