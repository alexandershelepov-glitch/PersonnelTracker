from __future__ import annotations

from typing import Any


def install_service_page_scroll(window: Any) -> None:
    """Make the growing Service page vertically scrollable without touching ui.py.

    v0.7 and v0.8 add independent QGroupBox widgets to the original Service
    page. Once enough blocks are installed, a plain QVBoxLayout tries to shrink
    every block to fit the window, which clips labels and can reduce buttons to
    thin strips. This adapter runs after all feature installers, moves the
    service blocks into a size-constrained scroll content widget and leaves the
    page title fixed at the top.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLayout, QScrollArea, QVBoxLayout, QWidget

    page = window.pages.widget(4)
    root = page.layout()
    if root is None or getattr(window, "_service_scroll_installed", False):
        return

    # The first item is the page title created by MainWindow._page(). Keep it
    # outside the scroll area so the section heading remains visible.
    title_item = root.itemAt(0)
    title_widget = title_item.widget() if title_item is not None else None

    content = QWidget(page)
    content.setObjectName("serviceScrollContent")
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 4, 4)
    content_layout.setSpacing(10)
    # Critical: the content keeps its natural minimum height instead of asking
    # Qt to compress every QGroupBox to the viewport height.
    content_layout.setSizeConstraint(QLayout.SetMinimumSize)

    # Remove everything except the title from the old layout. Feature modules
    # only add widgets plus a trailing stretch, so moving widgets is safe.
    while root.count() > 1:
        item = root.takeAt(1)
        widget = item.widget()
        if widget is not None:
            widget.setParent(content)
            content_layout.addWidget(widget)
        # Spacers/layout-only items are intentionally discarded; we add one
        # clean stretch at the end of the new content layout.

    content_layout.addStretch()

    scroll = QScrollArea(page)
    scroll.setObjectName("serviceScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    root.addWidget(scroll, 1)

    # Keep references for diagnostics and any future v0.8 additions.
    window.service_scroll = scroll
    window.service_scroll_content = content
    window.service_scroll_layout = content_layout
    window._service_scroll_installed = True

    # If the page title was unexpectedly absent, this still produces a usable
    # page; otherwise the title remains untouched at root index 0.
    if title_widget is not None:
        title_widget.setVisible(True)
