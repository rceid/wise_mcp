"""Who is better off? Gaps between women and men, age groups and education levels, measured as in
How's Life? 2024, Chapter 3.

Each group's value is divided by the population average and scored so that above 1 always means
better off: for "lower is better" measures such as homicides the ratio is flipped (average divided
by group). Groups within 0.03 of parity (1.0) count as "no clear difference". The gap between two
groups is the ratio of their scores, so women-vs-men below 1 means women are worse off.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from wise_mcp.analysis.data import BREAKDOWNS, AnalysisError, Breakdown, WellbeingData
from wise_mcp.catalog import OECD_MEMBERS, Measure

PARITY_TOLERANCE = 0.03

# Which groups to compare, as in the report: women vs men; younger vs middle-aged and older
# people. For education the report doesn't fix a pair, so this compares the lowest and highest.
PAIRS: dict[str, list[tuple[str, str]]] = {
    "sex": [("F", "M")],
    "age": [("YOUNG", "MID"), ("YOUNG", "OLD")],
    "education": [("ISCED11_1", "ISCED11_5T8")],
}


@dataclass(frozen=True)
class GroupGaps:
    measure: dict[str, Any]
    breakdown: str
    groups: pd.DataFrame  # one row per country and group: value, population value, score
    summary: pd.DataFrame  # one row per country: year, better-off group, gaps between groups
    oecd: dict[str, Any] | None  # the same for the OECD average
    caveats: list[str]


def group_gaps(
    data: WellbeingData, code: str, by: Breakdown = "sex", countries: list[str] | None = None
) -> GroupGaps:
    measure = data.measure(code)
    if measure.better == "target":
        raise AnalysisError(f"{data.name(code)} ({code}) is itself a gap, so it has no groups.")
    if by not in BREAKDOWNS:
        raise AnalysisError(f"`by` must be one of {list(BREAKDOWNS)}")
    countries = data.check_countries(countries)
    column, groups = BREAKDOWNS[by]

    # Each country's latest year with a value for every group and for the population as a whole.
    wide = data.series(code, by).pivot_table(
        index=["ref_area", "time_period"], columns=column, values="obs_value"
    )
    wide = wide.reindex(columns=list(groups))
    population = data.series(code).set_index(["ref_area", "time_period"])["obs_value"]
    wide = wide.join(population.rename("population"), how="inner").dropna()
    latest = wide.groupby(level="ref_area").tail(1).reset_index()
    members = latest[latest["ref_area"].isin(OECD_MEMBERS)]  # before filtering: always all
    if countries is not None:
        latest = latest[latest["ref_area"].isin(countries)]
    if latest.empty:
        raise AnalysisError(f"No complete {by} breakdown for {data.name(code)} ({code}).")

    long = latest.melt(
        id_vars=["ref_area", "time_period", "population"],
        value_vars=list(groups),
        var_name=column,
        value_name="obs_value",
    )
    long["score"] = _score(measure, long["obs_value"], long["population"])
    long[f"{column}_label"] = long[column].map(lambda g: data.label(column, g))
    long = long.sort_values(["ref_area", column], key=_group_order(column, groups))

    return GroupGaps(
        measure=data.describe(code),
        breakdown=by,
        groups=data.with_labels(long.reset_index(drop=True)),
        summary=data.with_labels(_summarise(data, measure, latest, by)),
        oecd=_oecd(data, measure, members, by) if not members.empty else None,
        caveats=_caveats(latest, long),
    )


def _score(measure: Measure, values: pd.Series, population: pd.Series | float) -> pd.Series:
    """Group values relative to the population, flipped where lower is better. A value of zero
    gives no score rather than an infinite one."""
    ratio = values / population if measure.better == "higher" else population / values
    return ratio.replace([np.inf, -np.inf], np.nan)


def _summarise(data: WellbeingData, measure: Measure, wide: pd.DataFrame, by: str) -> pd.DataFrame:
    column, groups = BREAKDOWNS[by]
    scores = pd.DataFrame(
        {g: _score(measure, wide[g], wide["population"]) for g in groups}, index=wide.index
    )
    summary = wide[["ref_area", "time_period"]].copy()
    summary["better_off"] = [_better_off(data, column, row) for _, row in scores.iterrows()]
    for a, b in PAIRS[by]:
        summary[f"{a}_vs_{b}"] = scores[a] / scores[b]
    return summary.reset_index(drop=True)


def _better_off(data: WellbeingData, column: str, scores: pd.Series) -> str:
    if scores.isna().any():
        return "not computable"
    if ((scores - 1).abs() <= PARITY_TOLERANCE).all():
        return "no clear difference"
    return data.label(column, scores.idxmax())


def _oecd(data: WellbeingData, measure: Measure, members: pd.DataFrame, by: str) -> dict[str, Any]:
    """Scores for the OECD average: the mean over members of each group and of the population."""
    column, groups = BREAKDOWNS[by]
    means = members[list(groups) + ["population"]].mean()
    scores = _score(measure, means[list(groups)], means["population"])
    return {
        "countries": len(members),
        "values": {data.label(column, g): float(means[g]) for g in groups},
        "population_value": float(means["population"]),
        "scores": {data.label(column, g): float(scores[g]) for g in groups},
        "better_off": _better_off(data, column, scores),
        "gaps": {f"{a}_vs_{b}": float(scores[a] / scores[b]) for a, b in PAIRS[by]},
    }


def _caveats(latest: pd.DataFrame, long: pd.DataFrame) -> list[str]:
    caveats = []
    first, last = int(latest["time_period"].min()), int(latest["time_period"].max())
    if first != last:
        caveats.append(f"Latest years with a complete breakdown differ, from {first} to {last}.")
    zero = long[long["score"].isna()]["ref_area"].unique().tolist()
    if zero:
        caveats.append(f"Some groups have a value of 0 in {', '.join(zero)}, so no ratio exists.")
    return caveats


def _group_order(column: str, groups: tuple[str, ...]):
    """Sort key keeping groups in their natural order (young, middle-aged, old)."""
    order = {g: i for i, g in enumerate(groups)}
    return lambda s: s.map(order) if s.name == column else s
