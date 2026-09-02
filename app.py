from __future__ import annotations

import sys
from pathlib import Path

from config import DB_FILENAME


def data_dir() -> Path:
    # Пока храним базу рядом с приложением в ./data.
    # Позже путь можно вынести в настройки / корпоративную папку.
    base = Path(__file__).resolve().parent
    return base / "data"


def database_path() -> Path:
    """The single, absolute SQLite location used by the desktop application."""
    return (data_dir() / DB_FILENAME).resolve()


def main() -> int:
    from ui import run_app
    db_path = database_path()
    print(f"Используется база данных: {db_path}")
    return run_app(db_path)


if __name__ == "__main__":
    sys.exit(main())
