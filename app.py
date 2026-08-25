from __future__ import annotations

import sys
from pathlib import Path

from config import DB_FILENAME


def data_dir() -> Path:
    # Пока храним базу рядом с приложением в ./data.
    # Позже путь можно вынести в настройки / корпоративную папку.
    base = Path(__file__).resolve().parent
    return base / "data"


def main() -> int:
    from ui import run_app
    db_path = data_dir() / DB_FILENAME
    return run_app(db_path)


if __name__ == "__main__":
    sys.exit(main())
