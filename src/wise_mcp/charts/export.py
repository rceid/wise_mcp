"""Charts as Vega-Lite specs (for tests and, in PR 5b, the interactive view) and as PNG images
(for any MCP client). vl-convert renders offline: no browser, no network."""

import json
from typing import Any

import vl_convert

from wise_mcp.charts.style import DARK_MARKS, config

THUMBNAIL_SCALE = 0.5
FULL_SCALE = 1.5


def spec(chart: Any, theme: str = "light") -> dict[str, Any]:
    """The chart's Vega-Lite spec with the house style applied, light or dark. Dark swaps every
    mark colour for its dark step, so the templates only ever name the light palette."""
    body = chart.to_dict()
    if theme == "dark":
        body = _recolour(body)
    return {**body, "config": config(theme)}


def _recolour(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _recolour(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_recolour(value) for value in node]
    if isinstance(node, str):
        return DARK_MARKS.get(node, node)
    return node


def png(chart: Any, scale: float = FULL_SCALE) -> bytes:
    return png_from_spec(spec(chart), scale)


def png_from_spec(vega_lite: dict[str, Any], scale: float = FULL_SCALE) -> bytes:
    """Render a finished spec. No network access: every chart carries its data inline."""
    return vl_convert.vegalite_to_png(json.dumps(vega_lite), scale=scale, allowed_base_urls=[])
