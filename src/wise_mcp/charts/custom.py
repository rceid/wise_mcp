"""Custom charts: for the rare question none of the templates fits, Claude writes a Vega-Lite spec
and the server draws it.

Claude writes JSON, never code, and never the data: the server injects one measure's rows, taken
from the same analysis functions as every other tool (OECD members only, each value with its year
and flag, the OECD average computed the How's Life? way). The spec can't load anything itself: any
`data`, `datasets` or `url` in it is refused, and rendering has no network access. The chart keeps
the house style and says, in its subtitle, that it isn't one of the standard views.
"""

import json
from typing import Any, Literal

import pandas as pd
from altair.vegalite.v6.schema import core

from wise_mcp import analysis, render
from wise_mcp.analysis import AnalysisError, WellbeingData
from wise_mcp.charts.catalog import Drawing
from wise_mcp.charts.style import config, subtitle
from wise_mcp.charts.templates import _about

Rows = Literal["latest", "series"]
MAX_SPEC_BYTES = 20_000
FORBIDDEN = {"data", "datasets", "url"}  # the server supplies the data; nothing is fetched
NOTE = "Custom chart drawn by Claude for this question: not one of wise_mcp's standard views."

# What Claude can encode, for the tool description.
FIELDS: dict[str, str] = {
    "latest": "country, code, year, value, flag, rank, oecd_average, better_than_oecd",
    "series": "country, code, year, period, value, flag (the OECD average as country "
    '"OECD average", code "OECD")',
}


def custom_chart(
    data: WellbeingData,
    measure: str,
    spec: dict[str, Any],
    rows: Rows = "latest",
    countries: list[str] | None = None,
    since: str = "2010",
) -> Drawing:
    """Draw Claude's Vega-Lite spec over one measure's rows: each country's latest value
    ("latest") or every value since a baseline ("series")."""
    _check(spec)
    if rows == "latest":
        result = analysis.compare_countries(data, measure, countries)
        values, table = _latest_rows(result), render.comparison(result)
    elif rows == "series":
        result = analysis.trend(data, measure, countries, since=since)
        values, table = _series_rows(result), render.trend(result)
    else:
        raise AnalysisError('`rows` must be "latest" or "series".')

    described = result.measure
    title = spec.get("title")
    text = title.get("text") if isinstance(title, dict) else title
    full = {
        **{key: value for key, value in spec.items() if key not in ("title", "config")},
        "data": {"values": values},
        "title": {
            "text": text or described["name"],
            "subtitle": subtitle(f"{_about(described)}.", NOTE),
        },
        "config": config(),
    }
    try:
        core.TopLevelSpec.from_dict(full)
    except Exception as exc:  # jsonschema's message for an anyOf schema runs to pages
        raise AnalysisError(f"The spec isn't valid Vega-Lite v6: {_explain(exc)}") from None
    return Drawing(chart=full, table=table)


def _explain(exc: Exception) -> str:
    """The offending value and the schema's complaint, e.g. "'barr' isn't allowed there
    ('boxplot' was expected)", from jsonschema's multi-page message."""
    lines = [line.strip() for line in str(exc).strip().splitlines()]
    first = lines[0][:200]
    if "On instance:" in lines:
        value = lines[lines.index("On instance:") + 1][:80]
        return f"{value} isn't allowed there ({first})."
    return f"{first}."


def _check(spec: Any) -> None:
    if not isinstance(spec, dict):
        raise AnalysisError("The spec must be a Vega-Lite JSON object.")
    if len(json.dumps(spec)) > MAX_SPEC_BYTES:
        raise AnalysisError(f"The spec is over {MAX_SPEC_BYTES // 1000} KB; keep it simple.")
    found = _forbidden_keys(spec)
    if found:
        raise AnalysisError(
            f"Leave out {', '.join(sorted(found))}: the server adds the data, and a spec can't "
            "load anything else."
        )


def _forbidden_keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        found = FORBIDDEN & set(node)
        for value in node.values():
            found |= _forbidden_keys(value)
        return found
    if isinstance(node, list):
        return set().union(*(_forbidden_keys(value) for value in node)) if node else set()
    return set()


def _latest_rows(result: analysis.Comparison) -> list[dict[str, Any]]:
    table = result.table
    average = result.oecd_average
    frame = pd.DataFrame(
        {
            "country": table["ref_area_label"],
            "code": table["ref_area"],
            "year": table["time_period"].astype(int),
            "value": table["obs_value"].astype(float),
            "flag": table["obs_status_label"].where(table["obs_status"] != "A", ""),
            "rank": table["rank"].astype("Float64"),
            "oecd_average": average.value if average else None,
            "better_than_oecd": table["better_than_oecd"],
        }
    )
    return _plain(frame)


def _series_rows(result: analysis.Trend) -> list[dict[str, Any]]:
    series = result.series
    frame = pd.DataFrame(
        {
            "country": series["ref_area_label"],
            "code": series["ref_area"],
            "year": series["time_period"],
            "period": series["period"] if "period" in series else series["time_period"].astype(str),
            "value": series["obs_value"].astype(float),
            "flag": series["obs_status_label"].where(series["obs_status"] != "A", ""),
        }
    )
    line = result.oecd_line
    if not line.empty:
        oecd = pd.DataFrame(
            {
                "country": "OECD average",
                "code": "OECD",
                "year": line["time_period"],
                "period": line["period"] if "period" in line else line["time_period"].astype(str),
                "value": line["obs_value"].astype(float),
                "flag": "",
            }
        )
        frame = pd.concat([frame, oecd], ignore_index=True)
    return _plain(frame)


def _plain(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """JSON-ready records: pandas' NA and numpy scalars don't serialise."""
    clean = frame.astype(object).where(frame.notna(), None)
    return [
        {key: (value.item() if hasattr(value, "item") else value) for key, value in row.items()}
        for row in clean.to_dict("records")
    ]
