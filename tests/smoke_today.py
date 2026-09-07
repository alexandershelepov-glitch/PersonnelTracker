"""Launch the real entry point against a disposable backup of an existing DB.

Usage: python tests/smoke_today.py /path/to/data/personnel.db /path/to/screenshots
The source database is opened read-only and is never used by MainWindow.
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as entry


def snapshot(path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        rows = {name: list(db.execute('SELECT * FROM "' + name.replace('"', '""') + '"'))
                for name in tables}
        return hashlib.sha256(repr(rows).encode()).hexdigest(), {k: len(v) for k, v in rows.items()}


def main():
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)
    before = snapshot(source)
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / 'data' / 'personnel.db'
        target.parent.mkdir()
        with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(target) as dst:
                src.backup(dst)
        settings = QSettings(str(Path(temp) / 'settings.ini'), QSettings.IniFormat)
        application = QApplication.instance() or QApplication([])
        errors = []

        def verify():
            try:
                window = next(w for w in application.topLevelWidgets() if hasattr(w, 'today_page'))
                assert window.pages.currentWidget() is window.today_page
                for theme in ('light', 'dark'):
                    window.theme_manager.apply(application, theme)
                    window._sync_theme_controls()
                    for width, height in ((760, 520), (1280, 850)):
                        window.resize(width, height)
                        application.processEvents()
                        assert window.today_page.grab().save(str(output / f'{theme}-{width}.png'))
                for index in (0, 1, 2, 3, 4, 5):
                    window._select_page(index)
                    application.processEvents()
                    assert window.pages.currentIndex() == index
                assert snapshot(target) == before, 'Database content changed during startup/UI checks'
                print('PASS: real app.main startup, navigation, themes, 760/1280 widths; DB unchanged')
                print('Database row counts:', before[1])
                window.close()
            except Exception as exc:
                errors.append(exc)
            finally:
                application.quit()

        QTimer.singleShot(800, verify)
        with patch.object(entry, 'database_path', return_value=target), \
             patch('ui.QSettings', return_value=settings), \
             patch('theme.QSettings', return_value=settings):
            entry.main()
        assert snapshot(source) == before, 'Source database changed'
        if errors:
            raise errors[0]


if __name__ == '__main__':
    main()
