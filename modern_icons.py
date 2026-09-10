"""Dependency-free outline icons for the modern PersonnelTracker UI.

The app is packaged as a standalone desktop bundle, so the visual layer keeps
icons in code instead of adding an external font or icon dependency.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def line_icon(kind: str, color: str, size: int = 20) -> QIcon:
    """Return a small Retina-friendly outline icon in the requested colour."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(1.65)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    if kind in {"today", "planning", "calendar"}:
        painter.drawRoundedRect(QRectF(3.0, 4.5, 14.0, 12.5), 2.2, 2.2)
        painter.drawLine(3.2, 8.0, 16.8, 8.0)
        painter.drawLine(6.2, 2.8, 6.2, 6.1)
        painter.drawLine(13.8, 2.8, 13.8, 6.1)
        if kind == "today":
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(8.15, 10.2, 3.7, 3.7))
        elif kind == "planning":
            painter.drawLine(6.0, 11.0, 10.0, 11.0)
            painter.drawLine(6.0, 14.0, 13.5, 14.0)
    elif kind == "people":
        painter.drawEllipse(QRectF(4.0, 3.2, 5.5, 5.5))
        painter.drawEllipse(QRectF(11.6, 4.6, 4.2, 4.2))
        painter.drawArc(QRectF(2.2, 8.5, 9.2, 8.3), 20 * 16, 140 * 16)
        painter.drawArc(QRectF(9.2, 9.0, 8.4, 7.2), 22 * 16, 128 * 16)
    elif kind == "settings":
        for y, knob in ((5.0, 7.0), (10.0, 13.0), (15.0, 9.0)):
            painter.drawLine(3.0, y, 17.0, y)
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(knob - 1.5, y - 1.5, 3.0, 3.0))
            painter.setBrush(Qt.NoBrush)
    elif kind == "search":
        painter.drawEllipse(QRectF(3.2, 3.2, 9.8, 9.8))
        painter.drawLine(12.0, 12.0, 17.0, 17.0)
    elif kind == "copy":
        painter.drawRoundedRect(QRectF(6.0, 5.0, 10.0, 11.0), 1.8, 1.8)
        painter.drawRoundedRect(QRectF(3.2, 2.3, 10.0, 11.0), 1.8, 1.8)
    elif kind == "open":
        painter.drawRoundedRect(QRectF(3.2, 4.0, 11.3, 12.4), 1.8, 1.8)
        painter.drawLine(10.5, 3.5, 16.7, 3.5)
        painter.drawLine(16.5, 3.7, 16.5, 9.7)
        painter.drawLine(16.2, 3.8, 9.4, 10.6)
    elif kind in {"reset", "refresh"}:
        painter.drawArc(QRectF(3.0, 3.0, 14.0, 14.0), 40 * 16, 285 * 16)
        painter.drawLine(3.9, 4.2, 3.3, 8.0)
        painter.drawLine(3.9, 4.2, 7.6, 4.8)
    elif kind == "plus":
        painter.drawLine(10.0, 4.0, 10.0, 16.0)
        painter.drawLine(4.0, 10.0, 16.0, 10.0)
    elif kind == "edit":
        painter.drawLine(4.0, 15.8, 6.2, 10.8)
        painter.drawLine(6.2, 10.8, 13.7, 3.3)
        painter.drawLine(13.7, 3.3, 16.6, 6.2)
        painter.drawLine(16.6, 6.2, 9.1, 13.7)
        painter.drawLine(4.0, 15.8, 9.1, 13.7)
        painter.drawLine(4.0, 15.8, 3.4, 16.6)
    elif kind == "delete":
        painter.drawRoundedRect(QRectF(5.2, 6.0, 9.6, 10.5), 1.5, 1.5)
        painter.drawLine(3.7, 5.0, 16.3, 5.0)
        painter.drawLine(7.2, 3.2, 12.8, 3.2)
        painter.drawLine(8.2, 8.0, 8.2, 14.0)
        painter.drawLine(11.8, 8.0, 11.8, 14.0)
    elif kind == "save":
        painter.drawRoundedRect(QRectF(3.5, 3.2, 13.0, 13.6), 1.8, 1.8)
        painter.drawRect(QRectF(6.0, 3.2, 7.0, 4.2))
        painter.drawRoundedRect(QRectF(6.2, 10.0, 7.6, 5.0), 1.2, 1.2)
    elif kind == "export":
        painter.drawRoundedRect(QRectF(4.0, 10.0, 12.0, 6.5), 1.8, 1.8)
        painter.drawLine(10.0, 3.0, 10.0, 12.0)
        painter.drawLine(6.8, 6.3, 10.0, 3.0)
        painter.drawLine(13.2, 6.3, 10.0, 3.0)
    elif kind == "backup":
        painter.drawRoundedRect(QRectF(3.5, 5.0, 13.0, 11.5), 2.0, 2.0)
        painter.drawLine(6.0, 5.0, 7.6, 2.8)
        painter.drawLine(14.0, 5.0, 12.4, 2.8)
        painter.drawLine(7.2, 10.8, 12.8, 10.8)
    elif kind == "restore":
        painter.drawArc(QRectF(3.0, 3.0, 14.0, 14.0), 80 * 16, 245 * 16)
        painter.drawLine(3.8, 4.0, 3.4, 8.0)
        painter.drawLine(3.8, 4.0, 7.5, 4.7)
        painter.drawLine(10.0, 6.5, 10.0, 10.5)
        painter.drawLine(10.0, 10.5, 13.0, 12.0)
    elif kind == "report":
        painter.drawRoundedRect(QRectF(4.0, 2.8, 12.0, 14.5), 1.8, 1.8)
        painter.drawLine(7.0, 7.0, 13.0, 7.0)
        painter.drawLine(7.0, 10.2, 13.0, 10.2)
        painter.drawLine(7.0, 13.4, 11.0, 13.4)
    elif kind == "back":
        painter.drawLine(4.0, 10.0, 16.0, 10.0)
        painter.drawLine(4.0, 10.0, 9.0, 5.0)
        painter.drawLine(4.0, 10.0, 9.0, 15.0)

    painter.end()
    return QIcon(pixmap)
