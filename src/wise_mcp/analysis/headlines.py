"""The headline indicators: country profiles and an overall well-being score, following How's
Life? 2024, Chapter 4 (note to Figure 4.5).

Each headline indicator is rescaled across OECD members from 0 (the worst member) to 1 (the best),
using each country's latest value after 2019. Scores are averaged within each dimension, so every
dimension counts the same however many indicators it has, then averaged across dimensions. With
equal weights this is the report's method; with custom weights per dimension it becomes the
Better Life Index's "create your own index".

The index is called "Better Life 36" for now: Better Life Index-style weighting over the 36 How's
Life? headline indicators (the Better Life Index itself uses a different set of 24). Like the
report, it keeps two separate scores: current well-being (24 indicators, 11 dimensions) and
resources for future well-being (12 indicators, 4 capitals).
"""

from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
import pandas as pd

from wise_mcp.analysis.data import AnalysisError, WellbeingData, goodness
from wise_mcp.catalog import FIRST_FUTURE_DIMENSION, Measure

Kind = Literal["current", "future"]
DIMENSIONS: dict[str, range] = {
    "current": range(1, FIRST_FUTURE_DIMENSION),
    "future": range(FIRST_FUTURE_DIMENSION, 16),
}
LATEST_AFTER = 2019  # "The latest year refers to the latest available year after 2019."
INDEX_NAME = "Better Life 36"  # working name, see the module docstring

# The headline for feeling safe at night is the gap between men and women, not the average. It's
# computed as men's share minus women's (percentage points), like the gender wage gap, where a
# positive gap means women are worse off. The goal is no gap.
FEELING_SAFE = "10_2"


@dataclass(frozen=True)
class Profile:
    ref_area: str
    name: str
    indicators: pd.DataFrame  # one row per headline indicator the country has data for
    overall: dict[str, Any]  # overall current and future scores, with rank among members
    strengths: list[str]  # headline indicators in the top third of OECD members
    weaknesses: list[str]  # ... and in the bottom third
    caveats: list[str]


@dataclass(frozen=True)
class Index:
    name: str  # e.g. "Better Life 36: current well-being"
    kind: str
    weights: dict[str, float]  # dimension name -> weight
    scores: pd.DataFrame  # one row per OECD member, best first
    dimension_scores: pd.DataFrame  # one row per country and dimension
    caveats: list[str]


def headline_scores(data: WellbeingData, kind: Kind = "current") -> pd.DataFrame:
    """Every member's latest value after 2019 for each headline indicator, with its 0-1 score
    and rank."""
    frames = []
    for measure in _headline_measures(data, kind):
        if measure.code == FEELING_SAFE:
            measure, series = _feeling_safe_gap(data)
        else:
            series = data.series(measure.code)
        latest = series[series["time_period"] > LATEST_AFTER].groupby("ref_area").tail(1)
        if latest.empty:
            continue
        good = goodness(measure, latest["obs_value"])
        low, high = good.min(), good.max()
        frames.append(
            latest.assign(
                code=measure.code,
                name=measure.name or data.name(measure.code),
                dimension=data.dimension(measure),
                dimension_number=measure.dimension,
                better=measure.better,
                score=(good - low) / (high - low) if high > low else np.nan,
                rank=good.rank(ascending=False, method="min").astype("Int64"),
                out_of=len(latest),
            )
        )
    if not frames:
        raise AnalysisError(f"No headline data for {kind} well-being after {LATEST_AFTER}.")
    return data.with_labels(pd.concat(frames, ignore_index=True))


def wellbeing_index(
    data: WellbeingData, weights: dict[Any, float] | None = None, kind: Kind = "current"
) -> Index:
    """Better Life 36: an overall score per OECD member (0-1, higher is better) across the
    current or future headline indicators.

    `weights` maps dimensions (number, e.g. 5, or name, e.g. "Health") to a weight of 0 or more;
    dimensions left out keep a weight of 1, and 0 drops a dimension. No weights reproduces the
    How's Life? 2024 method.
    """
    scores = headline_scores(data, kind)
    weight_by_number = _weights(data, weights, kind)

    by_dimension = (
        scores.groupby(["ref_area", "dimension_number", "dimension"])
        .agg(score=("score", "mean"), indicators=("score", "count"))
        .reset_index()
        .dropna(subset=["score"])
    )
    by_dimension["weight"] = by_dimension["dimension_number"].map(weight_by_number)
    weighted = by_dimension[by_dimension["weight"] > 0].assign(
        weighted=lambda d: d["score"] * d["weight"]
    )
    totals = weighted.groupby("ref_area").agg(
        weighted=("weighted", "sum"),
        weight=("weight", "sum"),
        dimensions=("dimension", "count"),
        indicators=("indicators", "sum"),
    )
    overall = pd.DataFrame(
        {
            "score": totals["weighted"] / totals["weight"],
            "dimensions": totals["dimensions"],
            "indicators": totals["indicators"],
        }
    ).reset_index()
    overall["rank"] = overall["score"].rank(ascending=False, method="min").astype("Int64")
    overall = data.with_labels(overall.sort_values("rank").reset_index(drop=True))

    total = len(_headline_measures(data, kind))
    fewest, most = int(overall["indicators"].min()), int(overall["indicators"].max())
    caveats = [
        "Covers OECD members only, as How's Life? does. Each indicator uses the latest value "
        f"after {LATEST_AFTER}, so years can differ between countries.",
        f"Countries have data for {fewest} to {most} of the {total} headline indicators. As in "
        "How's Life?, missing ones are left out of a country's score, which can over- or "
        "under-state it.",
    ]
    sparse = overall[overall["indicators"] < 0.75 * total]["ref_area"].tolist()
    if sparse:
        caveats.append(f"Scores for {', '.join(sparse)} rest on under three-quarters of them.")
    return Index(
        name=f"{INDEX_NAME}: {kind} well-being",
        kind=kind,
        weights={data.label("domain", f"HSL_{n}"): w for n, w in weight_by_number.items()},
        scores=overall,
        dimension_scores=data.with_labels(by_dimension.reset_index(drop=True)),
        caveats=caveats,
    )


def country_profile(data: WellbeingData, country: str) -> Profile:
    """A country's headline indicators against the OECD average and other members."""
    (ref_area,) = data.check_countries([country])
    frames, overall = [], {}
    for kind in DIMENSIONS:
        scores = headline_scores(data, kind)  # type: ignore[arg-type]
        averages = scores.groupby("code")["obs_value"].mean()
        mine = scores[scores["ref_area"] == ref_area]
        mine = mine.assign(kind=kind, oecd_average=mine["code"].map(averages))
        frames.append(mine)
        index = wellbeing_index(data, kind=kind).scores  # type: ignore[arg-type]
        row = index[index["ref_area"] == ref_area]
        overall[kind] = (
            {"score": float(row["score"].iloc[0]), "rank": int(row["rank"].iloc[0]),
             "out_of": len(index)}
            if not row.empty else None
        )  # fmt: skip

    indicators = pd.concat(frames, ignore_index=True)
    measures = {**data.measures, FEELING_SAFE: _feeling_safe_gap(data)[0]}
    indicators["better_than_oecd"] = [
        goodness(measures[row.code], row.obs_value) > goodness(measures[row.code], row.oecd_average)
        for row in indicators.itertuples()
    ]
    indicators["tier"] = [_tier(row.rank, row.out_of) for row in indicators.itertuples()]

    missing = [
        m.code for m in data.measures.values()
        if m.headline and m.code not in set(indicators["code"])
    ]  # fmt: skip
    caveats = []
    if missing:
        caveats.append(
            f"No data after {LATEST_AFTER} for {len(missing)} headline indicator(s): "
            + ", ".join(data.name(code) for code in missing)
            + "."
        )
    return Profile(
        ref_area=ref_area,
        name=data.label("ref_area", ref_area),
        indicators=indicators,
        overall=overall,
        strengths=indicators[indicators["tier"] == "top third"]["name"].tolist(),
        weaknesses=indicators[indicators["tier"] == "bottom third"]["name"].tolist(),
        caveats=caveats,
    )


def _headline_measures(data: WellbeingData, kind: Kind) -> list[Measure]:
    return [m for m in data.measures.values() if m.headline and m.dimension in DIMENSIONS[kind]]


def _feeling_safe_gap(data: WellbeingData) -> tuple[Measure, pd.DataFrame]:
    measure = replace(
        data.measure(FEELING_SAFE),
        better="target",
        target=0.0,
        name="Gender gap in feeling safe at night",
    )
    by_sex = data.series(FEELING_SAFE, "sex")
    wide = by_sex.pivot_table(
        index=["ref_area", "time_period"], columns="sex", values="obs_value"
    ).dropna()
    statuses = by_sex.pivot_table(
        index=["ref_area", "time_period"], columns="sex", values="obs_status", aggfunc="first"
    ).reindex(wide.index)
    gap = pd.DataFrame(
        {
            "obs_value": wide["M"] - wide["F"],
            # Keep a flag from either group (e.g. a series break) rather than dropping it.
            "obs_status": statuses["M"].where(statuses["M"] != "A", statuses["F"]),
        }
    ).reset_index()
    return measure, gap


def _weights(data: WellbeingData, weights: dict[Any, float] | None, kind: Kind) -> dict[int, float]:
    numbers = list(DIMENSIONS[kind])
    by_name = {data.label("domain", f"HSL_{n}").lower(): n for n in numbers}
    result = dict.fromkeys(numbers, 1.0)
    for key, weight in (weights or {}).items():
        number = key if isinstance(key, int) else by_name.get(str(key).lower())
        if number not in result:
            raise AnalysisError(
                f"Unknown {kind} well-being dimension {key!r}. Use one of: "
                + ", ".join(f"{n} ({data.label('domain', f'HSL_{n}')})" for n in numbers)
            )
        if not isinstance(weight, int | float) or weight < 0:
            raise AnalysisError(f"Weights must be numbers of at least 0, not {weight!r}.")
        result[number] = float(weight)
    if not any(result.values()):
        raise AnalysisError("At least one dimension needs a weight above 0.")
    return result


def _tier(rank: Any, out_of: int) -> str | None:
    """Top, middle or bottom third of OECD members with data."""
    if pd.isna(rank) or not out_of:
        return None
    if rank <= out_of / 3:
        return "top third"
    if rank > 2 * out_of / 3:
        return "bottom third"
    return "middle third"
