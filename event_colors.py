"""Stable, theme-aware colours for personnel events.

Every top-level EVENT_TYPES entry gets its own hue.  Subtypes intentionally
inherit their parent event colour so the planner stays readable instead of
turning into a dense rainbow.  Colours are presentation-only: no event or
availability semantics are encoded here.
"""
from __future__ import annotations

from PySide6.QtGui import QColor


# Explicit hues keep colours stable even if EVENT_TYPES is reordered later.
# Values are degrees on the HSV colour wheel.
EVENT_HUES: dict[str, int] = {
    "Отпуск": 38,
    "Больничный": 4,
    "Командировка": 210,
    "СВО": 346,
    "Выходной": 162,
    "Отгул": 58,
    "ММ": 276,
    "Другие объекты": 194,
    "Начальная подготовка": 128,
    "Самостоятельная подготовка": 108,
    "Подготовка руководителей": 92,
    "Плановая подготовка": 76,
    "Иная подготовка": 64,
    "Вновь принятые": 24,
    "Сдача периодической проверки": 302,
    "Сдача медкомиссии": 324,
    "Отсутствуют по иным причинам": 18,
    "Организация деятельности": 232,
}


def _blend(first: QColor, second: QColor, first_weight: float) -> QColor:
    weight = max(0.0, min(1.0, first_weight))
    inverse = 1.0 - weight
    return QColor(
        round(first.red() * weight + second.red() * inverse),
        round(first.green() * weight + second.green() * inverse),
        round(first.blue() * weight + second.blue() * inverse),
    )


def event_background(event_type: str, theme_manager) -> QColor:
    """Return a muted but distinct background for one top-level event type."""
    hue = EVENT_HUES.get(str(event_type), 220)
    dark = theme_manager.current_theme() == theme_manager.DARK
    # The pure colour provides identity; mixing with the theme panel keeps the
    # planner calm and readable in both themes.
    pure = QColor.fromHsv(hue, 150 if dark else 170, 205 if dark else 220)
    panel = theme_manager.color("panel_bg")
    return _blend(pure, panel, 0.42 if dark else 0.30)


def event_foreground(event_type: str, theme_manager) -> QColor:
    """Use the normal theme text colour over the deliberately muted background."""
    return theme_manager.color("text")
