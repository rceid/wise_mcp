"""The chart templates: each turns one analysis result into an Altair chart.

The methodology is drawn into every chart: each value carries its year, the OECD average is
shown as How's Life? computes it, flagged values (estimates, breaks) are marked, and the
direction that counts as better is stated in the subtitle. Nothing here computes statistics:
the analysis package does, and these functions only draw what it returns.
"""

from typing import Any

import altair as alt
import pandas as pd

from wise_mcp.analysis import Comparison, CountryTrends, GroupGaps, Index, Profile, Trend
from wise_mcp.analysis.data import BREAKDOWNS, AnalysisError
from wise_mcp.charts.style import (
    BAR,
    CATEGORICAL,
    CONTEXT,
    INK,
    INK_MUTED,
    INK_SECONDARY,
    ROW,
    SERIES,
    STATUS,
    SURFACE,
    WIDTH,
    subtitle,
)

# Line charts get the first four palette slots (a line chart only needs neighbouring colours to
# differ), with the country's name written at the end of each line.
LINE_COLORS = [*CATEGORICAL, "#eda100"]
MAX_LINES = len(LINE_COLORS)
MIN_HEIGHT = 3 * ROW  # a chart of one or two rows would otherwise be a thin strip
FLAG = "†"  # marks estimates, breaks and other flagged values in axis labels


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Plain Python values for Vega-Lite: pandas' NA and numpy scalars don't serialise."""
    clean = frame.astype(object).where(frame.notna(), None)
    return [
        {key: (value.item() if hasattr(value, "item") else value) for key, value in row.items()}
        for row in clean.to_dict("records")
    ]


def _direction(measure: dict[str, Any]) -> str:
    if measure["better"] == "target":
        target = measure["target"]
        return f"closer to {target:g} is better"
    return f"{measure['better']} is better"


def _about(measure: dict[str, Any]) -> str:
    unit = f"{measure['unit']}; " if measure["unit"] else ""
    return f"{unit}{_direction(measure)}"


def _titled(chart: alt.TopLevelMixin, title: str, *lines: str | None) -> Any:
    return chart.properties(title=alt.TitleParams(text=title, subtitle=subtitle(*lines)))


def _status_labels(statuses: pd.Series) -> pd.Series:
    """ "▲ improving" etc.: the glyph and the word travel with the status colour."""
    return statuses.map(lambda s: f"{STATUS[s][1]} {s}")


def _status_color(field: str, statuses: pd.Series) -> alt.Color:
    present = [s for s in STATUS if s in set(statuses)]
    return alt.Color(
        f"{field}:N",
        scale=alt.Scale(
            domain=[f"{STATUS[s][1]} {s}" for s in present], range=[STATUS[s][0] for s in present]
        ),
        legend=alt.Legend(title=None, columns=3),  # five on one row overflow the panel
    )


def _flagged(frame: pd.DataFrame) -> pd.Series:
    return frame["obs_status"].fillna("A") != "A"


def _country_labels(table: pd.DataFrame) -> pd.Series:
    flags = _flagged(table).map({True: f" {FLAG}", False: ""})
    return table["ref_area_label"] + " · " + table["time_period"].astype(str) + flags


def _rank_labels(table: pd.DataFrame) -> pd.Series:
    """ "10= France · 2023": the rank written in, "=" marking a tie, so a reader never counts
    rows (tied countries sit on separate rows but share a rank)."""
    labels = _country_labels(table)
    if table["rank"].isna().all():
        return labels
    tied = table["rank"].duplicated(keep=False)
    prefix = table["rank"].astype(str) + tied.map({True: "= ", False: ". "})
    return prefix + labels


def _flag_note(table: pd.DataFrame) -> str | None:
    if not _flagged(table).any():
        return None
    kinds = sorted(set(table.loc[_flagged(table), "obs_status_label"].str.lower()))
    return f"{FLAG} flagged value: {', '.join(kinds)}"


# --- Country rankings ------------------------------------------------------------------------


def ranked_bars(result: Comparison, highlight: list[str] | None = None) -> Any:
    """Countries best first, bars from zero, the countries asked about highlighted and an
    OECD-average line. Best when values start near zero (shares, rates)."""
    return _ranking(result, highlight, mark="bar")


def dot_plot(result: Comparison, highlight: list[str] | None = None) -> Any:
    """Like ranked_bars, but dots on a scale that needn't start at zero, so differences stay
    visible when every value is far from zero (life satisfaction 6-8, life expectancy 75-85)."""
    return _ranking(result, highlight, mark="point")


def _ranking(result: Comparison, highlight: list[str] | None, mark: str) -> Any:
    measure, table, average = result.measure, result.table.copy(), result.oecd_average
    table["label"] = _rank_labels(table)
    table["highlight"] = table["ref_area"].isin(highlight) if highlight else True
    order = table["label"].tolist()  # already best first (or alphabetical if not comparable)

    base = alt.Chart(alt.Data(values=_records(table))).encode(
        y=alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=220)),
        tooltip=[
            alt.Tooltip("ref_area_label:N", title="Country"),
            alt.Tooltip("time_period:Q", title="Year", format="d"),
            alt.Tooltip("obs_value:Q", title="Value", format=",.2f"),
            alt.Tooltip("rank:Q", title="Rank"),
            alt.Tooltip("obs_status_label:N", title="Status"),
        ],
    )
    color = alt.when(alt.datum.highlight).then(alt.value(SERIES)).otherwise(alt.value(CONTEXT))
    x_title = measure["unit"] or "Value"
    if mark == "bar":
        marks = base.mark_bar(size=BAR).encode(
            x=alt.X("obs_value:Q", title=x_title, scale=alt.Scale(zero=True)), color=color
        )
    else:
        marks = base.mark_point().encode(
            x=alt.X("obs_value:Q", title=x_title, scale=alt.Scale(zero=False, padding=12)),
            fill=color,
        )

    layers = [marks]
    if average:
        rule = pd.DataFrame(
            [{"x": average.value, "label": f"{average.label} average: {average.value:,.2f}"}]
        )
        reference = alt.Chart(alt.Data(values=_records(rule)))
        # The label goes on whichever side of the line has room, so it never runs off the chart.
        low = 0 if mark == "bar" else table["obs_value"].min()
        span = table["obs_value"].max() - low
        right_side = span <= 0 or (average.value - low) / span < 0.6
        layers += [
            reference.mark_rule(color=INK_SECONDARY, strokeWidth=1.5).encode(x="x:Q"),
            reference.mark_text(
                align="left" if right_side else "right",
                dx=4 if right_side else -4,
                dy=-6,
                color=INK_SECONDARY,
            ).encode(x="x:Q", y=alt.value(0), text="label:N"),
        ]
    if measure["better"] == "target" and measure["target"]:
        target = alt.Chart(alt.Data(values=[{"x": measure["target"]}]))
        layers.append(target.mark_rule(color=INK_MUTED, strokeWidth=1).encode(x="x:Q"))

    ranked = "Best first" if result.table["rank"].notna().any() else "Not ranked"
    return _titled(
        alt.layer(*layers).properties(width=WIDTH, height=ROW * len(table)),
        measure["name"],
        f"{_about(measure)}.",
        f"{ranked}, each country's latest year.",
        _flag_note(table),
    )


# --- Trends ----------------------------------------------------------------------------------


def trend_lines(result: Trend) -> Any:
    """One line per country (up to four) with the OECD average over a constant set of members,
    series breaks marked and each line labelled at its end."""
    measure, series = result.measure, result.series.copy()
    countries = sorted(series["ref_area_label"].unique())
    if not countries:
        raise AnalysisError(f"No data for these countries {result.period}.")
    if len(countries) > MAX_LINES:
        raise AnalysisError(
            f"Line charts show up to {MAX_LINES} countries; use change_arrows for more."
        )
    series["break"] = series["obs_status"] == "B"
    pooled = "period" in series
    if not pooled:
        series["period"] = series["time_period"].astype(int).astype(str)
    data = alt.Data(values=_records(series))
    color = alt.Color(
        "ref_area_label:N",
        scale=alt.Scale(domain=countries, range=LINE_COLORS[: len(countries)]),
        legend=alt.Legend(title=None) if len(countries) > 1 else None,
    )
    axis = alt.Axis(format="d", tickMinStep=1, labelOverlap=True, labelFlush=False)
    if pooled:  # a tick at the middle of each period, labelled with the period ("2014–16")
        ticks = series.drop_duplicates("period").set_index("time_period")["period"].sort_index()
        lookup = ", ".join(f"'{year:g}': '{label}'" for year, label in ticks.items())
        axis = alt.Axis(
            values=ticks.index.tolist(), labelExpr=f"{{{lookup}}}[datum.value]", labelFlush=False
        )
    x = alt.X("time_period:Q", title=None, scale=alt.Scale(nice=False), axis=axis)
    y = alt.Y("obs_value:Q", title=measure["unit"] or None, scale=alt.Scale(zero=False))
    tooltip = [
        alt.Tooltip("ref_area_label:N", title="Country"),
        alt.Tooltip("period:N", title="Period" if pooled else "Year"),
        alt.Tooltip("obs_value:Q", title="Value", format=",.2f"),
        alt.Tooltip("obs_status_label:N", title="Status"),
    ]
    lines = alt.Chart(data).mark_line().encode(x=x, y=y, color=color)
    # Dots mark the real values when there are few of them (pooled measures, or years missing),
    # so a straight line across the gaps doesn't pass for yearly data.
    gaps = series.groupby("ref_area_label")["time_period"].diff().gt(1).any()
    points = (
        alt.Chart(data)
        .mark_point(opacity=1 if pooled or gaps else 0, size=40)
        .encode(x=x, y=y, fill=color, tooltip=tooltip)
    )
    breaks = (
        alt.Chart(data)
        .transform_filter(alt.datum["break"])
        .mark_point(shape="diamond", size=110)
        .encode(x=x, y=y, fill=color, tooltip=tooltip)
    )
    ends = alt.Chart(data).transform_window(
        order="rank()", sort=[alt.SortField("time_period", order="descending")],
        groupby=["ref_area_label"],
    ).transform_filter(alt.datum.order == 1)  # fmt: skip
    layers = [
        lines,
        points,
        breaks,
        ends.mark_point().encode(x=x, y=y, fill=color),
        ends.mark_text(align="left", dx=8, color=INK).encode(x=x, y=y, text="ref_area_label:N"),
    ]

    oecd_note = None
    if not result.oecd_line.empty:
        members = int(result.oecd_line["countries"].iloc[0])
        line = result.oecd_line.assign(label=f"OECD average ({members} members)")
        oecd = alt.Chart(alt.Data(values=_records(line)))
        layers = [
            oecd.mark_line(color=INK_MUTED, strokeDash=[4, 3]).encode(x=x, y=y),
            oecd.mark_text(align="left", dx=8, color=INK_MUTED)
            .transform_window(order="rank()", sort=[alt.SortField("time_period", "descending")])
            .transform_filter(alt.datum.order == 1)
            .encode(x=x, y=y, text="label:N"),
            *layers,
        ]
        end = "period_end" if "period_end" in result.oecd_line else "time_period"
        last = int(result.oecd_line[end].max())
        oecd_note = (
            f"Dashed: OECD average over the {members} members with data in every year to {last}"
        )
        # The table's OECD average needs only the baseline and latest years, so it often covers
        # more members: say so, or the two figures look like a contradiction.
        if result.oecd and result.oecd["countries"] != members:
            oecd_note += f" (the table's average covers {result.oecd['countries']})"
        oecd_note += "."
    has_breaks = bool(series["break"].any())
    return _titled(
        alt.layer(*layers).properties(width=WIDTH, height=280),
        measure["name"],
        _about(measure) + ".",
        "One point per period (e.g. 2014–16): the OECD publishes a single value for each."
        if pooled
        else None,
        oecd_note,
        "◆ series break: the method changed, so the change across it may not be real."
        if has_breaks
        else None,
    )


def change_arrows(result: Trend) -> Any:
    """For each country, a line from its baseline value to its latest value, ending in a dot
    coloured by the How's Life? assessment, with the OECD average first and then countries from
    most to least improved. Works for any number of countries."""
    measure = result.measure
    rows = result.changes[result.changes["end_year"].notna()].copy()
    if rows.empty:
        raise AnalysisError(f"No country has data for {result.period}.")
    rows["label"] = (
        rows["ref_area_label"] + " · " + rows["start_year"].astype(str) + "–"
        + rows["end_year"].astype(str)
    )  # fmt: skip
    improvement = rows["end_value"] - rows["start_value"]
    if measure["better"] == "lower":
        improvement = -improvement
    elif measure["better"] == "target":
        improvement = (rows["start_value"] - measure["target"]).abs() - (
            rows["end_value"] - measure["target"]
        ).abs()
    rows = rows.assign(improvement=improvement).sort_values("improvement", ascending=False)
    if result.oecd:
        oecd = result.oecd
        first = {
            "label": f"OECD average ({oecd['countries']} members)",
            "ref_area_label": "OECD average",
            "start_value": oecd["start_value"],
            "end_value": oecd["end_value"],
            "change": oecd["change"],
            "assessment": oecd["assessment"],
        }
        rows = pd.concat([pd.DataFrame([first]), rows], ignore_index=True)
    rows["status"] = _status_labels(rows["assessment"])
    rows["glyph"] = rows["assessment"].map(lambda a: STATUS[a][1])
    columns = ["label", "ref_area_label", "start_value", "end_value", "change", "status", "glyph"]
    data = alt.Data(values=_records(rows[columns]))

    y = alt.Y("label:N", sort=rows["label"].tolist(), title=None, axis=alt.Axis(labelLimit=220))
    x = alt.X("start_value:Q", title=measure["unit"] or None, scale=alt.Scale(zero=False,
              padding=12))  # fmt: skip
    tooltip = [
        alt.Tooltip("ref_area_label:N", title="Country"),
        alt.Tooltip("start_value:Q", title="From", format=",.2f"),
        alt.Tooltip("end_value:Q", title="To", format=",.2f"),
        alt.Tooltip("change:Q", title="Change", format="+,.2f"),
        alt.Tooltip("status:N", title="Assessment"),
    ]
    chart = alt.Chart(data)
    layers = [
        chart.mark_rule(color=CONTEXT, strokeWidth=2).encode(x=x, x2="end_value:Q", y=y),
        chart.mark_point(filled=False, color=INK_MUTED, size=40, strokeWidth=1.5).encode(x=x, y=y),
        chart.mark_point().encode(
            x="end_value:Q",
            y=y,
            fill=_status_color("status", rows["assessment"]),
            tooltip=tooltip,
        ),  # fmt: skip
        # The glyph again in a column on the right, so the judgement never rests on colour.
        chart.mark_text(align="left", color=INK_SECONDARY).encode(
            x=alt.value(WIDTH + 10), y=y, text="glyph:N"
        ),
    ]
    threshold = measure["threshold"]
    rule_text = (
        f"Meaningful change: at least {threshold:g}"
        if threshold
        else "Any change counts"
        if threshold == 0
        else "No published threshold, so changes are not classed"
    )
    missing = result.changes[result.changes["end_year"].isna()]["ref_area"].tolist()
    # Wrapped, or a long list of countries widens the chart past the panel.
    missing_lines = [
        ("Not enough data: " if i == 0 else "") + ", ".join(missing[i : i + 14])
        for i in range(0, len(missing), 14)
    ]
    return _titled(
        alt.layer(*layers).properties(width=WIDTH, height=ROW * len(rows)),
        f"{measure['name']}: change {result.period}",
        f"{_about(measure)}.",
        "Open circle: baseline; dot: latest.",
        f"{rule_text} (How's Life? 2024).",
        *missing_lines,
    )


# --- Group gaps ------------------------------------------------------------------------------


def gap_dots(result: GroupGaps) -> Any:
    """One row per country with a dot per group (e.g. women and men), joined by a line: the
    longer the line, the bigger the gap. The OECD average comes first, then the widest gaps."""
    measure = result.measure
    column, groups = BREAKDOWNS[result.breakdown]
    names = dict(zip(result.groups[column], result.groups[f"{column}_label"], strict=True))
    groups = [g for g in groups if g in names]
    if len(groups) > len(CATEGORICAL):
        raise AnalysisError("Gap charts show at most three groups.")

    rows = result.groups.copy()
    rows["label"] = rows["ref_area_label"] + " · " + rows["time_period"].astype(str)
    rows["group"] = rows[f"{column}_label"]
    first_pair = next(c for c in result.summary.columns if "_vs_" in c)
    gap = result.summary.set_index("ref_area")[first_pair]
    rows["gap"] = rows["ref_area"].map((gap - 1).abs())
    order = rows.sort_values("gap", ascending=False)["label"].drop_duplicates().tolist()

    if result.oecd:
        oecd_label = f"OECD average ({result.oecd['countries']} members)"
        oecd_rows = pd.DataFrame(
            [{"label": oecd_label, "group": name, "obs_value": value}
             for name, value in result.oecd["values"].items()]
        )  # fmt: skip
        rows = pd.concat([oecd_rows, rows], ignore_index=True)
        order = [oecd_label, *order]

    labels = [names[g] for g in groups]
    data = alt.Data(values=_records(rows[["label", "group", "obs_value"]]))
    y = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))
    # No domain padding: it adds ticks beyond the data whose labels run into their neighbours.
    x = alt.X(
        "obs_value:Q",
        title=measure["unit"] or None,
        scale=alt.Scale(zero=False, nice=True),
        axis=alt.Axis(labelOverlap=True, tickCount=6),
    )
    span = (
        alt.Chart(data)
        .mark_rule(color=CONTEXT, strokeWidth=2)
        .encode(x="min(obs_value):Q", x2="max(obs_value):Q", y=y)
    )
    dots = (
        alt.Chart(data)
        .mark_point()
        .encode(
            x=x,
            y=y,
            fill=alt.Color(
                "group:N",
                scale=alt.Scale(domain=labels, range=CATEGORICAL[: len(labels)]),
                legend=alt.Legend(title=None),
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Country"),
                alt.Tooltip("group:N", title="Group"),
                alt.Tooltip("obs_value:Q", title="Value", format=",.2f"),
            ],
        )
    )
    return _titled(
        alt.layer(span, dots).properties(width=WIDTH, height=max(ROW * len(order), MIN_HEIGHT)),
        f"{measure['name']}: gaps by {result.breakdown}",
        f"{_about(measure)}.",
        "Widest gaps first; each country's latest year with every group.",
    )


# --- Country pictures ------------------------------------------------------------------------

TIERS = {
    "top third": STATUS["improving"][0],
    "middle third": STATUS["no clear change"][0],
    "bottom third": STATUS["deteriorating"][0],
}


def profile_scores(result: Profile) -> Any:
    """Each headline indicator as a 0-1 score (0 = the worst OECD member, 1 = the best),
    coloured by the country's third among members, with its rank written at the end."""
    rows = result.indicators.dropna(subset=["score"]).copy()
    rows["rank_text"] = rows["rank"].astype(str) + "/" + rows["out_of"].astype(str)
    charts = []
    for kind in ("current", "future"):
        part = rows[rows["kind"] == kind]
        if part.empty:
            continue
        order = part["name"].tolist()
        data = alt.Data(values=_records(part))
        y = alt.Y("name:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))
        x = alt.X("score:Q", title="Score (0 = worst member, 1 = best)", scale=alt.Scale(
            domain=[0, 1]))  # fmt: skip
        tiers = [t for t in TIERS if t in set(part["tier"])]
        bars = (
            alt.Chart(data)
            .mark_bar(size=BAR)
            .encode(
                x=x,
                y=y,
                color=alt.Color(
                    "tier:N",
                    scale=alt.Scale(domain=tiers, range=[TIERS[t] for t in tiers]),
                    legend=alt.Legend(title=None),
                ),
                tooltip=[
                    alt.Tooltip("dimension:N", title="Dimension"),
                    alt.Tooltip("name:N", title="Indicator"),
                    alt.Tooltip("time_period:Q", title="Year", format="d"),
                    alt.Tooltip("obs_value:Q", title="Value", format=",.2f"),
                    alt.Tooltip("oecd_average:Q", title="OECD average", format=",.2f"),
                    alt.Tooltip("rank_text:N", title="Rank"),
                ],
            )
        )
        ranks = (
            alt.Chart(data)
            .mark_text(align="left", dx=4, color=INK_SECONDARY)
            .encode(x=x, y=y, text="rank_text:N")
        )
        charts.append(
            alt.layer(bars, ranks).properties(
                # narrower bars leave room for the rank written after a full-length bar
                width=WIDTH - 60,
                height=ROW * len(part),
                title=f"{kind.capitalize()} well-being",
            )
        )
    if not charts:
        raise AnalysisError(f"No headline scores for {result.name}.")
    return _titled(
        alt.vconcat(*charts, spacing=24),
        f"{result.name}: How's Life? headline indicators",
        "Bar: 0-1 score, as in Better Life 36. Colour: the country's third by rank among members",
        "(rank written at the end). They can disagree when most members are bunched together.",
    )


def trend_grid(result: CountryTrends) -> Any:
    """Every headline indicator's change for the country and for the OECD average, as the
    How's Life? 2024 Chapter 4 country view: ▲ improving, ▼ deteriorating, ● no clear change."""
    rows = result.indicators
    cells = pd.concat(
        [
            rows.assign(column=result.name, assessment_=rows["assessment"]),
            rows.assign(column="OECD average", assessment_=rows["oecd_assessment"]),
        ],
        ignore_index=True,
    )
    cells["status"] = _status_labels(cells["assessment_"])
    cells["glyph"] = cells["assessment_"].map(lambda a: STATUS[a][1])
    cells["light_text"] = cells["assessment_"].isin(
        ["improving", "deteriorating", "no clear change"]
    )
    data = alt.Data(
        values=_records(cells[["name", "column", "status", "glyph", "light_text", "dimension"]])
    )
    y = alt.Y("name:N", sort=rows["name"].tolist(), title=None, axis=alt.Axis(labelLimit=300))
    x = alt.X("column:N", sort=[result.name, "OECD average"], title=None,
              axis=alt.Axis(orient="top", labelAngle=0, domain=False, ticks=False))  # fmt: skip
    boxes = (
        alt.Chart(data)
        .mark_rect(cornerRadius=3, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=x,
            y=y,
            color=_status_color("status", cells["assessment_"]),
            tooltip=[
                alt.Tooltip("dimension:N", title="Dimension"),
                alt.Tooltip("name:N", title="Indicator"),
                alt.Tooltip("column:N", title="For"),
                alt.Tooltip("status:N", title="Assessment"),
            ],
        )
    )
    glyphs = (
        alt.Chart(data)
        .mark_text(fontSize=11)
        .encode(
            x=x,
            y=y,
            text="glyph:N",
            color=alt.when(alt.datum.light_text).then(alt.value(SURFACE)).otherwise(alt.value(INK)),
        )
    )
    counts = [
        f"{kind.capitalize()} well-being: "
        + ", ".join(f"{counts[a]} {a}" for a in STATUS if counts.get(a))
        for kind, counts in result.summary.items()
    ]
    return _titled(
        alt.layer(boxes, glyphs).properties(width=150, height=ROW * len(rows)),
        f"{result.name}: headline indicators, change {result.period}",
        *counts,
        "Classed with How's Life? 2024 thresholds for meaningful change.",
    )


def index_ranking(result: Index, highlight: list[str] | None = None) -> Any:
    """Better Life 36 scores, best first, with the countries asked about highlighted."""
    table = result.scores.copy()
    table["highlight"] = table["ref_area"].isin(highlight) if highlight else True
    order = table["ref_area_label"].tolist()
    data = alt.Data(values=_records(table))
    color = alt.when(alt.datum.highlight).then(alt.value(SERIES)).otherwise(alt.value(CONTEXT))
    y = alt.Y("ref_area_label:N", sort=order, title=None)
    bars = (
        alt.Chart(data)
        .mark_bar(size=BAR)
        .encode(
            x=alt.X("score:Q", title="Score (0-1)", scale=alt.Scale(domain=[0, 1])),
            y=y,
            color=color,
            tooltip=[
                alt.Tooltip("ref_area_label:N", title="Country"),
                alt.Tooltip("rank:Q", title="Rank"),
                alt.Tooltip("score:Q", title="Score", format=".2f"),
                alt.Tooltip("indicators:Q", title="Indicators with data"),
            ],
        )
    )
    changed = {name: w for name, w in result.weights.items() if w != 1}
    weights = (
        "Weights: " + ", ".join(f"{name} ×{w:g}" for name, w in changed.items())
        if changed
        else "Equal weights, as in How's Life? 2024"
    )
    return _titled(
        bars.properties(width=WIDTH, height=ROW * len(table)),
        result.name,
        f"{weights}. 0 = the worst OECD member on every indicator, 1 = the best.",
    )
