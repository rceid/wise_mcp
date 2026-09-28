"""Charts as Vega-Lite specs (for tests and, in PR 5b, the interactive view) and as PNG images
(for any MCP client). vl-convert renders offline: no browser, no network."""

import json
from typing import Any

import vl_convert

from wise_mcp.charts.style import CONFIG

THUMBNAIL_SCALE = 0.5
FULL_SCALE = 1.5


def spec(chart: Any) -> dict[str, Any]:
    """The chart's Vega-Lite spec with the house style applied."""
    return {**chart.to_dict(), "config": CONFIG}


def png(chart: Any, scale: float = FULL_SCALE) -> bytes:
    return vl_convert.vegalite_to_png(json.dumps(spec(chart)), scale=scale)
