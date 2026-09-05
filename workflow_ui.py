from __future__ import annotations

from typing import Any, Callable


def install_workflow_ui(window: Any) -> None:
    """Reframe existing screens around a simple day-to-day workflow.

    This is intentionally a UI-only v0.8.3 adapter. It does not change the
    database, event rules, assignment history or backup logic. Existing v0.8
    dialogs remain the source of truth; this layer only puts their entry points
    where a user naturally looks for them.
    """
    from PySide6.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
    )

    if getattr(window, "_workflow_ui_installed", False):
        return

    # Keep the five-screen structure, but name every screen by the job it does.
    nav_names = {
        0: "Штат и назначения",
        1: "Работники",
        2: "Планирование",
        3: "Состояние и расход",
        4: "Настройки",
    }
    for index, text in nav_names.items():
        if index < len(getattr(window, "nav_buttons", [])):
            window.nav_buttons[index].setText(text)

    page_titles = {
        0: "Штат и назначения",
        1: "Работники",
        2: "Планирование отсутствий и мероприятий",
        3: "Состояние и расход",
        4: "Настройки и данные",
    }
    for index, text in page_titles.items():
        page = window.pages.widget(index)
        if page is None:
            continue
        for label in page.findChildren(QLabel):
            if label.objectName() == "pageTitle":
                label.setText(text)
                break

    service_page = window.pages.widget(4)

    def source_button(text: str):
        """Find the original feature button only inside Settings/Service."""
        if service_page is None:
            return None
        for button in service_page.findChildren(QPushButton):
            if button.text() == text:
                return button
        return None

    def forward_to_button(text: str) -> Callable[[], None]:
        def run() -> None:
            button = source_button(text)
            if button is not None:
                button.click()
        return run

    def open_planning() -> None:
        window._select_page(2)

    # Page 3 is the natural hub for answering "what is happening on this day?".
    state_page = window.pages.widget(3)
    state_root = state_page.layout() if state_page is not None else None
    if state_root is not None:
        hub = QGroupBox("Работа с выбранным днём")
        hub_layout = QVBoxLayout(hub)
        intro = QLabel(
            "Рабочий сценарий: выберите дату и посмотрите состояние людей. "
            "Если нужно изменить будущий день — перейдите в планирование и добавьте отпуск, "
            "больничный, командировку, мероприятие или другое событие. История нужна только для проверки прошлых назначений."
        )
        intro.setWordWrap(True)
        intro.setObjectName("secondaryText")
        hub_layout.addWidget(intro)

        actions = QHBoxLayout()
        state_button = QPushButton("Состояние на дату")
        state_button.setProperty("role", "primary")
        state_button.clicked.connect(forward_to_button("Открыть состояние на дату"))
        planning_button = QPushButton("Добавить отсутствие / мероприятие")
        planning_button.clicked.connect(open_planning)
        history_button = QPushButton("История назначений")
        history_button.clicked.connect(forward_to_button("История назначений"))
        assignment_snapshot = QPushButton("Штатный срез на дату")
        assignment_snapshot.clicked.connect(forward_to_button("Срез назначений на дату"))
        for button in (state_button, planning_button, history_button, assignment_snapshot):
            actions.addWidget(button)
        actions.addStretch()
        hub_layout.addLayout(actions)

        # MainWindow._page puts the title first and the original tab widget next.
        state_root.insertWidget(1, hub)

        tabs = state_page.findChild(QTabWidget)
        if tabs is not None:
            for index in range(tabs.count()):
                old = tabs.tabText(index)
                if old == "Сводка":
                    tabs.setTabText(index, "Расход и сводка")
                elif old == "Состояние на дату":
                    tabs.setTabText(index, "Быстрый просмотр")
            # The state-oriented tab is the more intuitive landing view.
            if tabs.count() > 1:
                tabs.setCurrentIndex(1)

    # v0.8 working features no longer belong in Settings. Their original
    # widgets remain alive (and provide the dialog callbacks), but are hidden.
    if service_page is not None:
        for group in service_page.findChildren(QGroupBox):
            if group.title() in {
                "История штатных назначений — v0.8",
                "Состояние личного состава на дату — v0.8.2",
            }:
                group.hide()

    # Rename the event-page action so the purpose is obvious without knowing
    # the internal term "event".
    planning_page = window.pages.widget(2)
    if planning_page is not None:
        for button in planning_page.findChildren(QPushButton):
            if button.text() == "Добавить":
                button.setText("Добавить отсутствие / мероприятие")
                break

    window._workflow_ui_installed = True
