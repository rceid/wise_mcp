"""Which charts fit a question, and how to draw one from its id.

A chart id spells out everything needed to draw it, such as
`dot_plot?measure=11_1&highlight=FRA`, so the server keeps no state between suggesting a chart
and showing it, and any client (or, in PR 5b, the chart gallery itself) can redraw it later.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from wise_mcp import analysis, render
from wise_mcp.analysis import AnalysisError, WellbeingData
from wise_mcp.analysis.headlines import INDEX_NAME
from wise_mcp.analysis.trends import Period
from wise_mcp.charts import templates

# A ranking is drawn as dots rather than bars when the smallest value is at least this share of
# the largest: bars must start at zero, which would squash differences between values bunched
# far from it (life satisfaction 5.7-8.4, life expectancy 75-85).
DOTS_FROM = 0.5
MAX_OPTIONS = 4


@dataclass(frozen=True)
class ChartOption:
    id: str
    title: str
    why: str


@dataclass(frozen=True)
class Drawing:
    chart: Any  # an Altair chart
    table: str  # the same data as Markdown: the chart's table view, readable by Claude too


def chart_id(name: str, **params: Any) -> str:
    """e.g. chart_id("dot_plot", measure="11_1", highlight=["FRA"])."""
    flat = {
        key: ",".join(value) if isinstance(value, list | tuple) else str(value)
        for key, value in params.items()
        if value not in (None, [], "")
    }
    return f"{name}?{urlencode(flat, safe=',')}" if flat else name


def _parse(id_: str) -> tuple[str, dict[str, Any]]:
    parts = urlsplit(id_)
    name = parts.path
    if name not in _BUILDERS:
        raise AnalysisError(f"Unknown chart {name!r}. Use suggest_charts to get chart ids.")
    params: dict[str, Any] = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    for key in ("countries", "highlight"):
        if key in params:
            params[key] = params[key].split(",")
    return name, params


def _canonical(id_: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """An id with its defaults filled in, so "change_arrows?measure=14_1" and
    "change_arrows?measure=14_1&since=2010" count as the same chart."""
    name, params = _parse(id_)
    if name in _SINCE:
        params.setdefault("since", "2010")
    return name, tuple(sorted((k, ",".join(v) if isinstance(v, list) else v)
                              for k, v in params.items()))  # fmt: skip


def draw(data: WellbeingData, id_: str) -> Drawing:
    """Draw the chart an id describes."""
    name, params = _parse(id_)
    try:
        return _BUILDERS[name](data, **params)
    except TypeError as exc:  # a parameter the chart doesn't take
        raise AnalysisError(f"Chart id {id_!r} doesn't fit {name}: {exc}") from None


def suggest(
    data: WellbeingData,
    measure: str | None = None,
    country: str | None = None,
    countries: list[str] | None = None,
    since: str = "2010",
) -> list[ChartOption]:
    """Up to four charts that suit a question about a measure, a country, or both, best first."""
    if measure is None and country is None and not countries:
        raise AnalysisError("Say what the chart is about: a measure, a country, or both.")
    focus = data.check_countries(countries or ([country] if country else None))

    if measure is None:  # a question about one country
        code = focus[0]
        name = data.label("ref_area", code)
        return [
            ChartOption(
                chart_id("trend_grid", country=code, since=since),
                f"{name}: which headline indicators improved {Period.since(since).label}",
                "The How's Life? country view: every headline indicator classed as improving, "
                "deteriorating or no clear change, next to the OECD average.",
            ),
            ChartOption(
                chart_id("profile_scores", country=code),
                f"{name}: strengths and weaknesses",
                "Each headline indicator scored 0-1 against other OECD members, with its rank.",
            ),
            ChartOption(
                chart_id("index_ranking", highlight=[code]),
                f"{INDEX_NAME}: where {name} ranks overall",
                "The overall score across all headline indicators, every member, "
                f"{name} highlighted.",
            ),
        ]

    described = data.describe(measure)
    options = []
    if data.measure(measure).comparable:
        values = analysis.compare_countries(data, measure).table["obs_value"]
        low, high = values.min(), values.max()
        bunched = low > 0 and low / high >= DOTS_FROM
        first, second = ("dot_plot", "ranked_bars") if bunched else ("ranked_bars", "dot_plot")
        why = {
            "dot_plot": f"Values are bunched far from zero ({low:,.2f} to {high:,.2f}), so dots "
            "on a zoomed scale show the differences that bars from zero would squash."
            if bunched
            else "Alternative view: dots on a scale zoomed to the data, stretching small "
            "differences.",
            "ranked_bars": "Bars from zero show each country's level against the OECD average."
            if not bunched
            else "Alternative view: bars from zero, keeping the true proportions between "
            "countries.",
        }
        style = {"dot_plot": "dots", "ranked_bars": "bars"}
        ranking = [
            ChartOption(
                chart_id(kind, measure=measure, highlight=focus),
                f"{described['name']}: countries ranked ({style[kind]}), latest year",
                why[kind],
            )
            for kind in (first, second)
        ]
        options.append(ranking[0])
    else:
        ranking = []

    if focus and len(focus) <= templates.MAX_LINES:
        options.append(
            ChartOption(
                chart_id("trend_lines", measure=measure, countries=focus, since=since),
                f"{described['name']} over time: {', '.join(focus)}",
                "One line per country against the OECD average, with series breaks marked.",
            )
        )
    options.append(
        ChartOption(
            chart_id("change_arrows", measure=measure, since=since),
            f"{described['name']}: change {Period.since(since).label}",
            "Every member's change from baseline to latest, classed with How's Life? thresholds.",
        )
    )
    breakdowns = data.coverage(measure)["breakdowns"]
    if breakdowns:
        by = "sex" if "sex" in breakdowns else breakdowns[0]
        options.append(
            ChartOption(
                chart_id("gap_dots", measure=measure, by=by, countries=focus),
                f"{described['name']}: gaps by {by}",
                f"Each group side by side for every country, widest gap first ({by} is one of "
                f"{len(breakdowns)} breakdowns available).",
            )
        )
    options += ranking[1:]
    return options[:MAX_OPTIONS]


_TAB_LABELS = {
    "ranked_bars": "Ranking (bars)", "dot_plot": "Ranking (dots)", "trend_lines": "Over time",
    "change_arrows": "Change, all countries", "trend_grid": "Trends",
    "profile_scores": "Strengths and weaknesses", "index_ranking": "Overall ranking",
}  # fmt: skip


def tab_label(id_: str) -> str:
    """A few words naming a chart, for a tab in the panel: "Over time", "Gaps by sex"."""
    name, params = _parse(id_)
    if name == "gap_dots":
        return f"Gaps by {params.get('by', 'sex')}"
    return _TAB_LABELS[name]


def related(data: WellbeingData, id_: str) -> list[ChartOption]:
    """The charts suggested for the same question as a chart id, the chart itself included: the
    tabs of the interactive panel. Charts without the data to draw are left out."""
    name, params = _parse(id_)
    countries = params.get("countries") or params.get("highlight")
    if "measure" in params:
        options = suggest(data, measure=params["measure"], countries=countries,
                          since=params.get("since", "2010"))  # fmt: skip
    else:  # a country picture; the index ranking names its country as the highlight
        country = params.get("country") or (countries[0] if countries else None)
        options = suggest(data, country=country, since=params.get("since", "2010"))
    # The chart asked for keeps its own id, so the panel can mark its tab as the current one.
    same = [o for o in options if _canonical(o.id) == _canonical(id_)]
    if same:
        options = [ChartOption(id_, o.title, o.why) if o in same else o for o in options]
    else:
        options = [ChartOption(id_, name.replace("_", " ").capitalize(), ""), *options]
    drawable = []
    for option in options:
        try:
            draw(data, option.id)
        except AnalysisError:
            continue
        drawable.append(option)
    return drawable


# --- Builders: analysis result -> chart and its table ----------------------------------------


def _ranking(kind: str) -> Callable[..., Drawing]:
    def build(data: WellbeingData, measure: str, highlight: list[str] | None = None) -> Drawing:
        highlight = data.check_countries(highlight)
        result = analysis.compare_countries(data, measure)
        chart = getattr(templates, kind)(result, highlight)
        table = analysis.compare_countries(data, measure, highlight) if highlight else result
        return Drawing(chart, render.comparison(table))

    return build


def _trend_lines(
    data: WellbeingData, measure: str, countries: list[str], since: str = "2010"
) -> Drawing:
    result = analysis.trend(data, measure, countries, since=since)
    return Drawing(templates.trend_lines(result), render.trend(result))


def _change_arrows(
    data: WellbeingData, measure: str, since: str = "2010", countries: list[str] | None = None
) -> Drawing:
    result = analysis.trend(data, measure, countries, since=since)
    return Drawing(templates.change_arrows(result), render.trend(result))


def _gap_dots(
    data: WellbeingData, measure: str, by: str = "sex", countries: list[str] | None = None
) -> Drawing:
    result = analysis.group_gaps(data, measure, by=by, countries=countries)  # type: ignore[arg-type]
    return Drawing(templates.gap_dots(result), render.gaps(result))


def _profile_scores(data: WellbeingData, country: str) -> Drawing:
    result = analysis.country_profile(data, country)
    return Drawing(templates.profile_scores(result), render.profile(result, INDEX_NAME))


def _trend_grid(data: WellbeingData, country: str, since: str = "2010") -> Drawing:
    result = analysis.country_trends(data, country, since=since)
    return Drawing(templates.trend_grid(result), render.country_trends(result))


def _index_ranking(
    data: WellbeingData, kind: str = "current", highlight: list[str] | None = None
) -> Drawing:
    result = analysis.wellbeing_index(data, kind=kind)  # type: ignore[arg-type]
    return Drawing(
        templates.index_ranking(result, data.check_countries(highlight)), render.index(result)
    )


_SINCE = {"trend_lines", "change_arrows", "trend_grid"}  # the charts taking a baseline year

_BUILDERS: dict[str, Callable[..., Drawing]] = {
    "ranked_bars": _ranking("ranked_bars"),
    "dot_plot": _ranking("dot_plot"),
    "trend_lines": _trend_lines,
    "change_arrows": _change_arrows,
    "gap_dots": _gap_dots,
    "profile_scores": _profile_scores,
    "trend_grid": _trend_grid,
    "index_ranking": _index_ranking,
}
