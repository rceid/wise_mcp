"""Analysis results as short Markdown for Claude to read: a title, one table, the OECD average and
the caveats. Tables name countries in full with their code, and every value keeps its year.
"""

from typing import Any

import pandas as pd

from wise_mcp.analysis import Comparison, GroupGaps, Index, Profile, Trend
from wise_mcp.analysis.data import BREAKDOWNS


def number(value: Any) -> str:
    """42,126 for large values, 7.35 or -0.30 for ordinary ones, 0.00312 for tiny ones, and –
    for missing ones."""
    if value is None or pd.isna(value):
        return "–"
    value = float(value)
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 0.01 or value == 0:
        return f"{value:.2f}"
    return f"{value:.3g}"


def signed(value: Any) -> str:
    text = number(value)
    return f"+{text}" if text != "–" and float(value) > 0 else text


def table(header: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def heading(measure: dict[str, Any], suffix: str = "") -> str:
    unit = f", {measure['unit']}" if measure["unit"] else ""
    if measure["better"] == "target":
        direction = f"closer to {number(measure['target'])} is better"
    else:
        direction = f"{measure['better']} is better"
    return f"**{measure['name']}** ({measure['code']}{unit}; {direction}){suffix}"


def caveats(items: list[str], note: str | None = None) -> str:
    items = list(items) + ([f"About this measure: {note}"] if note else [])
    return "Caveats:\n" + "\n".join(f"- {item}" for item in items) if items else ""


def join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


def _text(value: Any) -> str:
    """Missing values come back from pandas as NaN, which would print as "nan"."""
    return "" if value is None or pd.isna(value) else str(value).replace("_", " ")


def country(row: Any) -> str:
    return f"{row.ref_area_label} ({row.ref_area})"


def measures(found: pd.DataFrame, query: str) -> str:
    if found.empty:
        return f'No measures match "{query}". Try broader words, such as a dimension ("health").'
    rows = [
        [row.code, row.name, row.dimension, row.better, _text(row.headline)]
        for row in found.itertuples()
    ]
    return join(
        f'Measures matching "{query}", best match first:',
        table(["Code", "Name", "Dimension", "Better", "Headline type"], rows),
    )


def description(measure: dict[str, Any], coverage: dict[str, Any]) -> str:
    threshold = measure["threshold"]
    change = (
        f"a change of at least {number(threshold)}"
        if threshold
        else "any change"
        if threshold == 0
        else "no fixed threshold published"
    )
    by = ", ".join(coverage["breakdowns"]) or "none"
    lines = [
        f"- OECD label: {measure['oecd_label']}",
        f"- Dimension: {measure['dimension']}",
        f"- Headline indicator: {(measure['headline'] or 'no').replace('_', ' ')}",
        f"- Meaningful change (How's Life? 2024): {change}",
        f"- Data: {coverage['countries']} OECD members, {coverage['first_year']}-"
        f"{coverage['last_year']}; breakdowns: {by}",
    ]
    if measure["note"]:
        lines.append(f"- Note: {measure['note']}")
    return join(heading(measure), "\n".join(lines))


def comparison(result: Comparison) -> str:
    average = result.oecd_average
    rows = [
        [
            "–" if pd.isna(row.rank) else row.rank,
            country(row),
            row.time_period,
            number(row.obs_value),
            "–" if pd.isna(row.better_than_oecd) else "better" if row.better_than_oecd else "worse",
            "" if row.obs_status == "A" else row.obs_status_label,
        ]
        for row in result.table.itertuples()
    ]
    return join(
        heading(result.measure),
        f"{average.label} average: {number(average.value)} (latest years {average.years})"
        if average
        else "",
        table(["Rank", "Country", "Year", "Value", "vs OECD average", "Flag"], rows),
        caveats(result.caveats, result.measure["note"]),
    )


def trend(result: Trend) -> str:
    oecd = result.oecd
    threshold = result.measure["threshold"]
    rows = [
        [
            country(row),
            "–" if pd.isna(row.start_year) else f"{row.start_year}: {number(row.start_value)}",
            "–" if pd.isna(row.end_year) else f"{row.end_year}: {number(row.end_value)}",
            signed(row.change),
            row.assessment,
            "yes" if row.series_break else "",
        ]
        for row in result.changes.itertuples()
    ]
    return join(
        heading(result.measure, f": change {result.period}"),
        "Meaningful change: "
        + (
            f"at least {number(threshold)}"
            if threshold
            else "any change"
            if threshold == 0
            else "no fixed threshold, so changes are not classed"
        ),  # fmt: skip
        f"OECD average over the {oecd['countries']} members with both years: "
        f"{number(oecd['start_value'])} to {number(oecd['end_value'])} "
        f"({signed(oecd['change'])}), {oecd['assessment']}"
        if oecd
        else "",
        table(["Country", "From", "To", "Change", "Assessment", "Series break"], rows),
        caveats(result.caveats),
    )


def gaps(result: GroupGaps) -> str:
    column, groups = BREAKDOWNS[result.breakdown]
    names = dict(zip(result.groups[column], result.groups[f"{column}_label"], strict=True))
    groups = [g for g in groups if g in names]
    values = result.groups.pivot_table(index="ref_area", columns=column, values="obs_value")
    pairs = [c for c in result.summary.columns if "_vs_" in c]
    pair_names = [" vs ".join(names.get(g, g) for g in pair.split("_vs_")) for pair in pairs]

    rows = [
        [country(row), row.time_period]
        + [number(values.loc[row.ref_area, g]) for g in groups]
        + [row.better_off]
        + [number(getattr(row, pair)) for pair in pairs]
        for row in result.summary.itertuples()
    ]
    oecd = result.oecd
    oecd_line = (
        f"OECD average ({oecd['countries']} members): "
        + ", ".join(f"{name} {number(v)}" for name, v in oecd["values"].items())
        + f"; better off: {oecd['better_off']}; "
        + ", ".join(f"{pair_names[i]} {number(v)}" for i, v in enumerate(oecd["gaps"].values()))
        if oecd
        else ""
    )
    return join(
        heading(result.measure, f": gaps by {result.breakdown}"),
        "How to read the ratios: each group's value relative to the population average, scored so "
        "above 1 means better off. A ratio below 1 means the first group is worse off than the "
        "second. Groups within 0.03 of parity show no clear difference (How's Life? 2024).",
        oecd_line,
        table(["Country", "Year", *[names[g] for g in groups], "Better off", *pair_names], rows),
        caveats(result.caveats),
    )


def profile(result: Profile, index_name: str) -> str:
    overall = [
        f"{kind} well-being {number(scores['score'])}, rank {scores['rank']} of {scores['out_of']}"
        for kind, scores in result.overall.items()
        if scores
    ]
    rows = [
        [
            row.dimension,
            row.name,
            row.time_period,
            number(row.obs_value),
            number(row.oecd_average),
            "better" if row.better_than_oecd else "worse",
            f"{row.rank}/{row.out_of}",
            row.tier or "–",
        ]
        for row in result.indicators.itertuples()
    ]
    return join(
        f"**{result.name} ({result.ref_area}): How's Life? headline indicators**",
        f"{index_name} score (0-1, equal weights): " + "; ".join(overall) if overall else "",
        "Strengths (top third of OECD members): " + (", ".join(result.strengths) or "none"),
        "Weaknesses (bottom third): " + (", ".join(result.weaknesses) or "none"),
        table(
            ["Dimension", "Indicator", "Year", "Value", "OECD average", "vs OECD", "Rank", "Tier"],
            rows,
        ),
        caveats(result.caveats),
    )


def index(result: Index) -> str:
    changed = {name: w for name, w in result.weights.items() if w != 1}
    weights = (
        "Weights: " + ", ".join(f"{name} x{w:g}" for name, w in changed.items())
        + "; every other dimension x1"
        if changed
        else "Weights: equal, as in How's Life? 2024"
    )  # fmt: skip
    rows = [
        [row.rank, country(row), number(row.score), row.dimensions, row.indicators]
        for row in result.scores.itertuples()
    ]
    return join(
        f"**{result.name}** (0 = the worst OECD member on every indicator, 1 = the best)",
        weights,
        table(["Rank", "Country", "Score", "Dimensions", "Indicators"], rows),
        caveats(result.caveats),
    )
