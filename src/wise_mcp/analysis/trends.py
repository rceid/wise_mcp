"""Is life getting better? Change over time, judged the way How's Life? 2024 does it.

A country is "improving" or "deteriorating" when the change between a baseline year and the latest
year is at least the indicator's threshold for meaningful change (measures.yaml), and shows "no
clear change" otherwise. Baselines follow How's Life? 2024, Box 2.1: around 2010 (the earliest year
in 2010-15) for the medium term, 2019 (the latest year in 2016-19) for the period since the
pandemic, compared with the latest year after 2019.
"""

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from wise_mcp.analysis.data import AnalysisError, WellbeingData, goodness
from wise_mcp.catalog import OECD_MEMBERS, Measure

Assessment = Literal[
    "improving", "deteriorating", "no clear change", "no threshold", "insufficient data"
]

# Values carry up to ~10 decimals, so 7.2 - 6.9 comes out as 0.29999999999999982. Without a
# tolerance a change of exactly the threshold would be missed.
_TOLERANCE = 1e-9


_CHANGE_TYPES = {
    "start_year": "Int64", "start_value": "Float64", "end_year": "Int64", "end_value": "Float64",
    "change": "Float64",
}  # fmt: skip


@dataclass(frozen=True)
class Period:
    """Which two years to compare for each country."""

    label: str
    baseline_from: int
    baseline_to: int
    baseline_pick: Literal["earliest", "latest"]  # which year in the baseline window
    end_after: int  # the end is the latest year after this one

    @classmethod
    def since(cls, since: int | str) -> "Period":
        if str(since) == "2010":
            return cls("since around 2010", 2010, 2015, "earliest", 2019)
        if str(since) == "2019":
            return cls("since 2019 (before the pandemic)", 2016, 2019, "latest", 2019)
        try:
            year = int(since)
        except ValueError:
            raise AnalysisError(f"`since` must be a year, not {since!r}") from None
        return cls(f"since {year}", year, year + 5, "earliest", year)


@dataclass(frozen=True)
class Trend:
    measure: dict[str, Any]
    period: str
    changes: pd.DataFrame  # one row per country: baseline, end, change, assessment
    series: pd.DataFrame  # every year from each country's baseline to its end, for charts
    oecd: dict[str, Any] | None  # the same assessment for the OECD average
    caveats: list[str]


def assess(measure: Measure, start: float, end: float) -> Assessment:
    """Improving, deteriorating or no clear change, against the measure's threshold."""
    if measure.threshold is None:
        return "no threshold"
    improvement = goodness(measure, end) - goodness(measure, start)
    if measure.threshold == 0:  # "any change different from zero"
        meaningful = abs(improvement) > _TOLERANCE
    else:
        meaningful = abs(improvement) >= measure.threshold - _TOLERANCE
    if not meaningful:
        return "no clear change"
    return "improving" if improvement > 0 else "deteriorating"


def trend(
    data: WellbeingData,
    code: str,
    countries: list[str] | None = None,
    since: int | str = 2010,
) -> Trend:
    measure = data.measure(code)
    countries = data.check_countries(countries)
    period = Period.since(since)
    series = data.series(code)
    if countries is not None and not series["ref_area"].isin(countries).any():
        raise AnalysisError(f"No data for {data.name(code)} ({code}) in {countries}.")

    # Every country is assessed so the OECD average covers all members, even when only a few
    # countries are shown.
    rows, windows = [], []
    for ref_area, country in series.groupby("ref_area"):
        row = {"ref_area": ref_area, **_change(measure, country, period)}
        rows.append(row)
        if pd.notna(row["end_year"]):
            years = country["time_period"].between(row["start_year"], row["end_year"])
            windows.append(country[years])
    changes = data.with_labels(pd.DataFrame(rows).astype(_CHANGE_TYPES))
    window = pd.concat(windows) if windows else series.iloc[0:0]
    oecd = _oecd_change(measure, changes)
    if countries is not None:
        changes = changes[changes["ref_area"].isin(countries)]
        window = window[window["ref_area"].isin(countries)]

    return Trend(
        measure=data.describe(code),
        period=period.label,
        changes=changes.reset_index(drop=True),
        series=data.with_labels(window.reset_index(drop=True)),
        oecd=oecd,
        caveats=_caveats(measure, changes),
    )


def _change(measure: Measure, country: pd.DataFrame, period: Period) -> dict[str, Any]:
    empty = {
        "start_year": pd.NA, "start_value": pd.NA, "end_year": pd.NA, "end_value": pd.NA,
        "change": pd.NA, "assessment": "insufficient data", "series_break": False,
    }  # fmt: skip
    in_window = country[country["time_period"].between(period.baseline_from, period.baseline_to)]
    if in_window.empty:
        return empty
    start = in_window.iloc[0] if period.baseline_pick == "earliest" else in_window.iloc[-1]
    after = country[country["time_period"] > max(period.end_after, start["time_period"])]
    if after.empty:
        return empty
    end = after.iloc[-1]

    between = country["time_period"].between(start["time_period"] + 1, end["time_period"])
    return {
        "start_year": int(start["time_period"]),
        "start_value": float(start["obs_value"]),
        "end_year": int(end["time_period"]),
        "end_value": float(end["obs_value"]),
        "change": float(end["obs_value"] - start["obs_value"]),
        "assessment": assess(measure, start["obs_value"], end["obs_value"]),
        # A break means the method changed at some point, so part of the change may not be real.
        "series_break": bool((country.loc[between, "obs_status"] == "B").any()),
    }


def _oecd_change(measure: Measure, changes: pd.DataFrame) -> dict[str, Any] | None:
    """The OECD average at baseline and at the end, over the same members (members with both
    values), so a change in which countries report can't masquerade as a change in well-being."""
    both = changes[changes["ref_area"].isin(OECD_MEMBERS) & changes["end_year"].notna()]
    if both.empty:
        return None
    start, end = float(both["start_value"].mean()), float(both["end_value"].mean())
    return {
        "countries": len(both),
        "start_value": start,
        "end_value": end,
        "change": end - start,
        "assessment": assess(measure, start, end),
    }


def _caveats(measure: Measure, changes: pd.DataFrame) -> list[str]:
    caveats = []
    if measure.threshold is None:
        caveats.append(
            "How's Life? publishes no fixed threshold for this measure, so changes are shown "
            "without being classed as improving or deteriorating."
            + (f" {measure.note}" if measure.note else "")
        )
    breaks = changes[changes["series_break"]]["ref_area"].tolist()
    if breaks:
        caveats.append(
            f"Series breaks in {', '.join(breaks)}: the method changed during the period, so part "
            "of the change may reflect that rather than real change."
        )
    missing = changes[changes["assessment"] == "insufficient data"]["ref_area"].tolist()
    if missing:
        caveats.append(f"Not enough data for the period in {', '.join(missing)}.")
    return caveats
