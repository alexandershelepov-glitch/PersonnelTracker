from __future__ import annotations

import os
import sys
from pathlib import Path

from config import DB_FILENAME

APP_SUPPORT_DIRNAME = "PersonnelTracker"


def is_frozen() -> bool:
    """Return True when running from a frozen desktop bundle."""
    return bool(getattr(sys, "frozen", False))


def source_root() -> Path:
    return Path(__file__).resolve().parent


def windows_app_data_root() -> Path:
    """Writable per-user root for the frozen Windows build.

    ``%LOCALAPPDATA%`` is the documented per-user location for mutable
    application data and is never shared between users. If the environment
    variable is missing (unusual, but possible in stripped environments), fall
    back to the conventional ``~/AppData/Local`` path so the application still
    starts with a predictable location instead of writing next to the .exe.
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_SUPPORT_DIRNAME
    return Path.home() / "AppData" / "Local" / APP_SUPPORT_DIRNAME


def data_dir() -> Path:
    """Return the writable application-data directory for the current runtime.

    Source/development runs keep using the repository-local ``./data`` folder
    so the existing working setup remains unchanged. A frozen macOS app stores
    mutable data outside the .app bundle, under the user's Application Support
    directory, so replacing the application cannot replace the database. A
    frozen Windows build stores it under ``%LOCALAPPDATA%\\PersonnelTracker``,
    never next to the portable ``.exe``.
    """
    if is_frozen() and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SUPPORT_DIRNAME / "data"
    if is_frozen() and sys.platform == "win32":
        return windows_app_data_root() / "data"
    return source_root() / "data"


def database_path() -> Path:
    """The single absolute SQLite location used by the desktop application."""
    return (data_dir() / DB_FILENAME).resolve()
