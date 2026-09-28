"""One visual style for every chart: thin marks, hairline chrome, and colour only where it means
something. Colours come from a validated, colour-blind-safe palette (the data-viz reference
palette); nothing here is OECD branding.

Colour jobs:
- One series: every mark in SERIES. When a question is about particular countries, they stay in
  SERIES and the rest drop to CONTEXT (the "emphasis" form).
- Groups (e.g. women and men): CATEGORICAL slots in fixed order, at most three, the most that
  stay distinguishable for every kind of colour vision when any two marks can sit side by side
  (checked with the palette validator). The third is below 3:1 contrast, so every chart ships
  with its data table as text.
- Judgements (improving, deteriorating...): STATUS colours, always with a glyph and a word.
"""

from typing import Any

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
FONT = "system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"

SERIES = "#2a78d6"
CONTEXT = "#c3c2b7"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a"]

# Assessment -> (colour, glyph). The glyph and the word always travel with the colour.
STATUS: dict[str, tuple[str, str]] = {
    "improving": ("#0ca30c", "▲"),
    "deteriorating": ("#d03b3b", "▼"),
    "no clear change": ("#898781", "●"),
    "no threshold": ("#c3c2b7", "○"),
    "insufficient data": ("#e1e0d9", "–"),
}

WIDTH = 520  # plot width in px
ROW = 20  # px per country or indicator row
BAR = 14  # bar thickness in px, within the 24px cap

SOURCE = "Source: OECD How's Life? well-being database. Methods: How's Life? 2024."

# Vega-Lite config applied to every chart (see charts.render.spec).
CONFIG: dict[str, Any] = {
    "background": SURFACE,
    "font": FONT,
    "padding": 16,
    "view": {"stroke": None},
    "title": {
        "anchor": "start",
        "color": INK,
        "fontSize": 15,
        "fontWeight": 600,
        "subtitleColor": INK_SECONDARY,
        "subtitleFontSize": 12,
        "subtitlePadding": 6,
        "offset": 14,
    },
    "axis": {
        "domainColor": AXIS,
        "gridColor": GRID,
        "gridWidth": 1,
        "tickColor": AXIS,
        "labelColor": INK_SECONDARY,
        "labelFontSize": 11,
        "titleColor": INK_SECONDARY,
        "titleFontSize": 11,
        "titleFontWeight": 400,
    },
    "axisY": {"grid": False},
    "legend": {
        "labelColor": INK_SECONDARY,
        "labelFontSize": 11,
        "title": None,
        "orient": "top",
        "symbolSize": 80,
    },
    "text": {"color": INK_SECONDARY, "fontSize": 11},
    "line": {"strokeWidth": 2, "strokeCap": "round", "strokeJoin": "round"},
    "point": {"size": 80, "filled": True, "stroke": SURFACE, "strokeWidth": 2, "opacity": 1},
    "bar": {"cornerRadiusEnd": 4},
}


def subtitle(*lines: str | None) -> list[str]:
    """Subtitle lines under the title, always ending with the source."""
    return [line for line in lines if line] + [SOURCE]
