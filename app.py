from __future__ import annotations

import sys
from pathlib import Path

from config import APP_NAME, DB_FILENAME


def data_dir() -> Path:
    # Рабочая база остаётся локальной рядом с приложением в ./data.
    # Резервные ZIP-копии могут храниться в отдельной папке, выбранной в UI.
    base = Path(__file__).resolve().parent
    return base / "data"


def database_path() -> Path:
    """The single, absolute SQLite location used by the desktop application."""
    return (data_dir() / DB_FILENAME).resolve()


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from assignment_history_compat import install_assignment_history_features
    from backup_local import install_backup_features
    from csv_data import install_csv_features
    from service_page_scroll import install_service_page_scroll
    from temporal_snapshot import install_temporal_snapshot_features
    from theme import ThemeManager
    from ui import MainWindow
    from workflow_ui import install_workflow_ui

    db_path = database_path()
    print(f"Используется база данных: {db_path}")

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    ThemeManager().apply(app)
    window = MainWindow(db_path)
    install_backup_features(window)
    install_csv_features(window)
    install_assignment_history_features(window)
    install_temporal_snapshot_features(window)
    # The Service page must become scrollable before v0.8.3 hides the working
    # history/snapshot groups and moves their entry points into the daily hub.
    install_service_page_scroll(window)
    install_workflow_ui(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
