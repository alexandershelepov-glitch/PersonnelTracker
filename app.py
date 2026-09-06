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
    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication

    from assignment_history_compat import install_assignment_history_features
    from backup_local import install_backup_features
    from composition_ui import install_composition_ui
    from csv_data import install_csv_features
    from employee_profile_ui import install_employee_profile_ui
    from navigation_context import install_context_navigation
    from planning_ui import install_planning_ui
    from service_page_scroll import install_service_page_scroll
    from temporal_snapshot import install_temporal_snapshot_features
    from theme import ThemeManager
    from ui import MainWindow
    from workflow_ui import install_workflow_ui

    db_path = database_path()
    print(f"Используется база данных: {db_path}")

    # The application UI is Russian; set one Qt-wide locale so month/day names
    # in calendars, planners and date widgets never fall back to English on a
    # system whose desktop locale is different.
    QLocale.setDefault(QLocale("ru_RU"))

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
    # Composition reuses the existing SHDS widgets, so it is installed after
    # the v0.8.3 workflow shell but before context-aware Back navigation.
    install_composition_ui(window)
    # The profile layer patches the existing EmployeeDialog in-place so every
    # current entry point opens the same redesigned employee profile.
    install_employee_profile_ui(window)
    # Planning reuses the same events/editors while adding month graph + list.
    install_planning_ui(window)
    # Context navigation is installed last: it distinguishes a sidebar jump
    # from entering the same root screen through a nested working scenario.
    install_context_navigation(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
