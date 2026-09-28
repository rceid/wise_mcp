"""The interactive chart panel: an MCP App, a ui:// HTML page that Claude Desktop shows in the
chat when show_chart is called. It draws the same Vega-Lite specs as the PNGs, with hover
tooltips, tabs for the other charts suggested for the question, and Claude Desktop's theme.
"""

from functools import cache
from importlib.resources import files

URI = "ui://wise-mcp/chart.html"

_BUNDLES = {
    "/*VEGA*/": "vega.min.js",
    "/*VEGA_LITE*/": "vega-lite.min.js",
    "/*VEGA_EMBED*/": "vega-embed.min.js",
    "/*VEGA_INTERPRETER*/": "vega-interpreter.js",
}


@cache
def chart_html() -> str:
    """The panel with Vega inlined: the host's default CSP allows inline scripts but no outside
    domains, and inlining keeps the demo offline."""
    folder = files("wise_mcp.app")
    html = folder.joinpath("chart.html").read_text()
    for marker, name in _BUNDLES.items():
        code = folder.joinpath("vendor", name).read_text().replace("</script", "<\\/script")
        html = html.replace(marker, code)
    return html
