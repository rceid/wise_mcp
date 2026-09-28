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

WIDTH = 440  # plot width in px: charts fit the ~710px Claude Desktop panel
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
        "frame": "bounds",  # start at the chart's left edge, not after the row labels
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
    # The reference palette's eight slots in their fixed order, for custom charts (templates set
    # their colours explicitly).
    "range": {"category": [*CATEGORICAL, "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]},
}


# Diverging pair (for "better or worse than the OECD average"): blue <-> red with a grey midpoint,
# as the reference palette specifies. Blue always means better, whichever direction is better.
BETTER = SERIES
WORSE = "#e34948"  # categorical red, not the reserved status red
NEUTRAL = "#f0efec"

# --- Dark mode (the interactive panel follows Claude Desktop's theme; PNGs stay light) ---------
# Each colour's dark step from the same validated palette, not an automatic inversion. Series:
# the reference palette's dark column, re-run through the validator on the dark surface (#1a1a19):
# the three group colours pass all-pairs, the four line colours pass adjacent. Greys keep about the
# same contrast against the surface as in light mode (context 1.93:1 vs 1.75:1). Status colours
# are fixed across modes, except the two greys ("no threshold", "insufficient data").
DARK_SURFACE = "#1a1a19"
DARK_MARKS: dict[str, str] = {
    SURFACE: DARK_SURFACE,  # gaps between cells and rings around dots
    INK: "#ffffff",
    INK_SECONDARY: "#c3c2b7",
    SERIES: "#3987e5",  # also categorical slot 1
    CATEGORICAL[1]: "#d95926",
    CATEGORICAL[2]: "#199e70",
    "#eda100": "#c98500",  # fourth line colour
    CONTEXT: "#4a4945",  # also "no threshold"
    STATUS["insufficient data"][0]: "#383835",
    WORSE: "#e66767",
    NEUTRAL: "#383835",
}
DARK_CHROME = {
    "surface": DARK_SURFACE, "ink": "#ffffff", "secondary": "#c3c2b7", "muted": INK_MUTED,
    "grid": "#2c2c2a", "axis": "#383835",
}  # fmt: skip


def config(theme: str = "light") -> dict[str, Any]:
    """The Vega-Lite config for a theme: CONFIG, or the same with dark chrome."""
    if theme != "dark":
        return CONFIG
    c = DARK_CHROME
    return {
        **CONFIG,
        "background": c["surface"],
        "title": {**CONFIG["title"], "color": c["ink"], "subtitleColor": c["secondary"]},
        "axis": {
            **CONFIG["axis"],
            "domainColor": c["axis"],
            "gridColor": c["grid"],
            "tickColor": c["axis"],
            "labelColor": c["secondary"],
            "titleColor": c["secondary"],
        },  # fmt: skip
        "legend": {**CONFIG["legend"], "labelColor": c["secondary"]},
        "text": {**CONFIG["text"], "color": c["secondary"]},
        "point": {**CONFIG["point"], "stroke": c["surface"]},
        "range": {
            "category": [
                "#3987e5",
                "#d95926",
                "#199e70",
                "#c98500",
                "#d55181",
                "#008300",
                "#9085e9",
                "#e66767",
            ]
        },  # fmt: skip
    }


def subtitle(*lines: str | None) -> list[str]:
    """Subtitle lines under the title, always ending with the source."""
    return [line for line in lines if line] + [SOURCE]
