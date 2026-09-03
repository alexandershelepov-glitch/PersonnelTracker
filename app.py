from __future__ import annotations

import sys
from pathlib import Path

from config import APP_NAME, DB_FILENAME


def data_dir() -> Path:
    # Пока храним базу рядом с приложением в ./data.
    # Позже путь можно вынести в настройки / корпоративную папку.
    base = Path(__file__).resolve().parent
    return base / "data"


def database_path() -> Path:
    """The single, absolute SQLite location used by the desktop application."""
    return (data_dir() / DB_FILENAME).resolve()


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from backup import install_backup_features
    from theme import ThemeManager
    from ui import MainWindow

    db_path = database_path()
    print(f"Используется база данных: {db_path}")

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    ThemeManager().apply(app)
    window = MainWindow(db_path)
    install_backup_features(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
