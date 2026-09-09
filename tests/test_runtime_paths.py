from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import runtime_paths
from config import DB_FILENAME


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
