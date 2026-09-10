"""Final user-facing version/text cleanup before the v1.0 candidate.

Presentation only. Keeps historical implementation comments intact while
removing old development-version wording from the visible application UI.
"""
from __future__ import annotations

from typing import Any

from config import APP_VERSION


def install_release_polish_ui(window: Any) -> None:
    from PySide6.QtWidgets import QLabel

    if getattr(window, "_release_polish_ui_installed", False):
        return

    window.setWindowTitle(f"PersonnelTracker — v{APP_VERSION}")

    sidebar = getattr(window, "modern_sidebar", None)
    if sidebar is None:
        from PySide6.QtWidgets import QFrame
        sidebar = window.findChild(QFrame, "sidebar")
    if sidebar is not None:
        for label in sidebar.findChildren(QLabel):
            if label.objectName() == "appSubtitle" and label.text().startswith("v"):
                label.setText(f"v{APP_VERSION}")

    replacements = {
        "Рабочие выгрузки на основе уже существующих данных приложения. Первый отчёт — действующий личный состав.":
            "Рабочие отчёты и выгрузки на основе данных приложения.",
        "Источник — исторический срез v0.8.2. «Недоступные» — это существующее состояние доступности сервиса, поэтому сюда входят и выходные по графику.":
            "Состояние рассчитывается по историческим данным на выбранную дату. В «Недоступные» входят также выходные по графику.",
        "История ведётся с момента включения учёта v0.8. Более ранние назначения приложение не восстанавливает задним числом.":
            "История отображается с момента начала её ведения в приложении. Более ранние назначения автоматически не восстанавливаются.",
    }

    def clean_labels(root) -> None:
        for label in root.findChildren(QLabel):
            replacement = replacements.get(label.text())
            if replacement is not None:
                label.setText(replacement)

    clean_labels(window)

    # Report views are created lazily. Patch only their constructors so the
    # same user-facing cleanup is applied when a report dialog is opened.
    for attr in (
        "personnel_roster_view_type",
        "date_state_report_view_type",
        "assignment_history_report_view_type",
    ):
        view_type = getattr(window, attr, None)
        if view_type is None or getattr(view_type, "_release_text_polished", False):
            continue
        original_init = view_type.__init__

        def make_init(initializer):
            def wrapped(view, *args, **kwargs):
                initializer(view, *args, **kwargs)
                clean_labels(view)
            return wrapped

        view_type.__init__ = make_init(original_init)
        view_type._release_text_polished = True

    window._release_polish_ui_installed = True
