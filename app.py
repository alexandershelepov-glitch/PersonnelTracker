from __future__ import annotations

import sys

from config import APP_NAME
from runtime_paths import data_dir, database_path


def main() -> int:
    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication

    from assignment_history_compat import install_assignment_history_features
    from assignment_history_report_ui import install_assignment_history_report_ui
    from backup_local import install_backup_features
    from composition_ui import install_composition_ui
    from csv_data import install_csv_features
    from date_state_report_ui import install_date_state_report_ui
    from employee_profile_ui import install_employee_profile_ui
    from events_report_ui import install_events_report_ui
    from interface_polish import install_interface_polish
    from manual_team_ui import install_manual_team_ui
    from navigation_context import install_context_navigation
    from planning_ui import install_planning_ui
    from planning_usability import install_planning_usability
    from reports_ui import install_reports_ui
    from semi_auto_team_ui import install_semi_auto_team_ui
    from service_page_scroll import install_service_page_scroll
    from staffing_report_ui import install_staffing_report_ui
    from tab_theme_fix import install_tab_theme_fix
    from temporal_snapshot import install_temporal_snapshot_features
    from theme import ThemeManager
    from ui import MainWindow
    from workflow_ui import install_workflow_ui
    from workspace_resize_ui import install_workspace_resize_ui

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
    install_reports_ui(window)
    install_staffing_report_ui(window)
    install_date_state_report_ui(window)
    install_events_report_ui(window)
    install_assignment_history_report_ui(window)
    # The Service page must become scrollable before v0.8.3 hides the working
    # history/snapshot groups and moves their entry points into the daily hub.
    install_service_page_scroll(window)
    install_workflow_ui(window)
    # Composition reuses the existing SHDS widgets, so it is installed after
    # the v0.8.3 workflow shell but before context-aware Back navigation.
    install_composition_ui(window)
    # Manual team formation fills the Composition placeholder while reusing
    # Today-state semantics and the existing transactional batch editor.
    install_manual_team_ui(window)
    # Semi-auto mode ranks candidates but never persists a proposal. Final
    # creation still goes through the same BatchEventDialog/service rules.
    install_semi_auto_team_ui(window)
    # The profile layer patches the existing EmployeeDialog in-place so every
    # current entry point opens the same redesigned employee profile.
    install_employee_profile_ui(window)
    # Planning reuses the same events/editors while adding month graph + list.
    install_planning_ui(window)
    # Keep split planner rows visually locked and allow quick event creation by
    # clicking an employee name without changing event persistence semantics.
    install_planning_usability(window)
    # Context navigation distinguishes sidebar roots from nested working paths.
    install_context_navigation(window)
    # Final UI pass comes last so it sees every page/widget installed above.
    install_interface_polish(window)
    # macOS document-mode tabs can ignore parts of the dark Qt palette; force
    # the final tab strip to use the application's own theme colours.
    install_tab_theme_fix(window)
    # User-resizable table columns and summary splitters are applied after all
    # other UI layers so their geometry is not overwritten later in startup.
    install_workspace_resize_ui(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
