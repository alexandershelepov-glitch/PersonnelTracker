from __future__ import annotations

import sys
from pathlib import Path

from config import DB_FILENAME

APP_SUPPORT_DIRNAME = "PersonnelTracker"


def is_frozen() -> bool:
    """Return True when running from a frozen desktop bundle."""
    return bool(getattr(sys, "frozen", False))


def source_root() -> Path:
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """Return the writable application-data directory for the current runtime.

    Source/development runs keep using the repository-local ``./data`` folder
    so the existing working setup remains unchanged. A frozen macOS app stores
    mutable data outside the .app bundle, under the user's Application Support
    directory, so replacing the application cannot replace the database.
    """
    if is_frozen() and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SUPPORT_DIRNAME / "data"
    return source_root() / "data"


def database_path() -> Path:
    """The single absolute SQLite location used by the desktop application."""
    return (data_dir() / DB_FILENAME).resolve()
