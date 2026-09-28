"""The How's Life? data prepared for analysis: every observation, what each code means, and the
measure metadata from measures.yaml.

Everything else in this package builds on two things defined here: `WellbeingData.series`, which
picks out the right rows for a measure, and `goodness`, which puts any measure on a scale where
higher always means better for well-being.

The analysis covers the 38 OECD members only, as How's Life? 2024 does. The database also holds
partner and accession countries (Brazil, Romania...) and, in future well-being, a published "OECD"
aggregate row; `series` leaves all of them out.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from wise_mcp.catalog import OECD_MEMBERS, Measure, load_measures
from wise_mcp.config import DATAFLOWS
from wise_mcp.store import DataStore

TOTAL = "_T"

Breakdown = Literal["sex", "age", "education"]
# Breakdown -> (column, groups in display order)
BREAKDOWNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "sex": ("sex", ("F", "M")),
    "age": ("age", ("YOUNG", "MID", "OLD")),
    "education": ("education_lev", ("ISCED11_1", "ISCED11_2_3", "ISCED11_5T8")),
}
_GROUP_COLUMNS = [column for column, _ in BREAKDOWNS.values()]
# Words too common to help a search ("deaths of despair" should not match every "of").
_FILLER = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}


class AnalysisError(ValueError):
    """A question the data can't answer, with a message meant for the person asking."""


def goodness(measure: Measure, values: Any) -> Any:
    """Values on a scale where higher always means better: the value itself, its negative, or
    minus its distance from the target. Works on a number or a pandas Series."""
    if measure.better == "higher":
        return values
    if measure.better == "lower":
        return -values
    return -abs(values - measure.target)


def period_label(start: int, end: int) -> str:
    """ "2014–16", or "2019" for a single year."""
    if start == end:
        return str(start)
    if start // 100 == end // 100:
        return f"{start}–{end % 100:02d}"
    return f"{start}–{end}"


def periods(series: pd.DataFrame, by: str | None = "ref_area") -> pd.DataFrame:
    """A pooled measure's series (see measures.yaml) with one row per period instead of per year.

    The OECD publishes these measures as one value per period of up to three years, repeated for
    every year in it, so a period is a run of consecutive years with the same value (for each
    `by` group, e.g. country). Adds `period_start`, `period_end` and `period` ("2014–16"), and
    moves `time_period` to the period's middle so a chart puts the point where it belongs. A
    series break anywhere in the period flags the whole period.
    """
    if series.empty:
        return series.assign(period_start=[], period_end=[], period=[])
    keys = [by] if by else []
    frame = series.sort_values([*keys, "time_period"]).reset_index(drop=True)
    new = (frame["obs_value"].diff() != 0) | (frame["time_period"].diff() != 1)
    if by:
        new |= frame[by] != frame[by].shift()
    block = new.cumsum()
    grouped = frame.groupby(block)
    rows = grouped.first()
    rows["period_start"] = grouped["time_period"].min()
    rows["period_end"] = grouped["time_period"].max()
    if "obs_status" in frame:
        broken = grouped["obs_status"].agg(lambda s: (s == "B").any())
        rows.loc[broken, "obs_status"] = "B"
    rows["period"] = [
        period_label(a, b) for a, b in zip(rows["period_start"], rows["period_end"], strict=True)
    ]
    rows["time_period"] = (rows["period_start"] + rows["period_end"]) / 2
    return rows.reset_index(drop=True)


def period_of(series: pd.DataFrame, ref_area: str, year: int) -> str:
    """The period ("2023–25") a country's value for `year` belongs to, in a pooled series."""
    rows = periods(series[series["ref_area"] == ref_area])
    match = rows[(rows["period_start"] <= year) & (rows["period_end"] >= year)]
    return match["period"].iloc[0] if not match.empty else str(year)


def pooled_caveat(names: list[str], series: pd.DataFrame, ref_area: str, years: list[int]) -> str:
    """Warn that years in a pooled measure stand for whole periods, with examples for one
    country (e.g. "2025 stands for 2023–25")."""
    examples = " and ".join(
        f"{year} stands for {period_of(series, ref_area, year)}" for year in dict.fromkeys(years)
    )
    subject = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    verb = "is" if len(names) == 1 else "are"
    return (
        f"{subject} {verb} published as one value per period of up to three years, repeated for "
        f"every year in it, so a year shown stands for its whole period (e.g. {examples})."
    )


@dataclass(frozen=True)
class WellbeingData:
    observations: pd.DataFrame  # current and future well-being, as stored by DataStore
    labels: dict[str, dict[str, str]]  # column -> code -> English label
    measures: dict[str, Measure]  # from measures.yaml

    @classmethod
    def from_store(cls, store: DataStore) -> "WellbeingData":
        observations = pd.concat(
            [store.observations(name) for name in DATAFLOWS], ignore_index=True
        )
        return cls(observations, store.labels(), load_measures())

    def measure(self, code: str) -> Measure:
        try:
            return self.measures[code]
        except KeyError:
            raise AnalysisError(
                f"Unknown measure {code!r}. Use find_measures to look up measure codes."
            ) from None

    def label(self, column: str, code: str) -> str:
        return self.labels.get(column, {}).get(code, code)

    def name(self, code: str) -> str:
        """The How's Life? name where the report has one, otherwise the API label."""
        return self.measure(code).name or self.label("measure", code)

    def dimension(self, measure: Measure) -> str:
        return self.label("domain", f"HSL_{measure.dimension}")

    def check_countries(self, countries: list[str] | None) -> list[str] | None:
        """ISO codes for countries given as codes ("FRA") or English names ("France")."""
        if countries is None:
            return None
        areas = self.labels.get("ref_area", {})
        by_name = {name.lower(): code for code, name in areas.items()}
        codes, unknown = [], []
        for country in countries:
            code = country.upper() if country.upper() in areas else by_name.get(country.lower())
            (codes if code else unknown).append(code or country)
        if unknown:
            raise AnalysisError(
                f"Unknown country {unknown}. Use ISO codes such as FRA, or English names."
            )
        partners = [c for c in codes if c not in OECD_MEMBERS]
        if partners:
            raise AnalysisError(
                f"{', '.join(self.label('ref_area', c) for c in partners)}: not OECD member(s). "
                "The analysis covers the 38 OECD members only, as How's Life? 2024 does."
            )
        return codes

    def series(self, code: str, breakdown: Breakdown | None = None) -> pd.DataFrame:
        """One measure's observations for every OECD member and year: population totals, or each
        group of a breakdown (e.g. women and men). Sorted by country and year."""
        measure = self.measure(code)
        obs = self.observations
        rows = obs[(obs["measure"] == code) & obs["ref_area"].isin(OECD_MEMBERS)]

        if breakdown is None:
            rows = rows[(rows[_GROUP_COLUMNS] == TOTAL).all(axis=1)]
        else:
            if breakdown not in BREAKDOWNS:
                raise AnalysisError(f"Breakdown must be one of {list(BREAKDOWNS)}")
            column, groups = BREAKDOWNS[breakdown]
            others = [c for c in _GROUP_COLUMNS if c != column]
            rows = rows[rows[column].isin(groups) & (rows[others] == TOTAL).all(axis=1)]
            if rows.empty:
                raise AnalysisError(f"{self.name(code)} ({code}) has no breakdown by {breakdown}.")

        if measure.unit:
            rows = rows[rows["unit_measure"] == measure.unit]
        units = rows["unit_measure"].unique()
        if len(units) > 1:
            raise AnalysisError(
                f"{code} is published in several units {list(units)}: set `unit` in measures.yaml."
            )

        keep = ["ref_area", "time_period", "obs_value", "obs_status"]
        if breakdown is not None:
            keep.insert(1, BREAKDOWNS[breakdown][0])
        return rows[keep].sort_values(keep[:-2]).reset_index(drop=True)

    def with_labels(self, table: pd.DataFrame) -> pd.DataFrame:
        """Add country names and status labels next to the codes."""
        extra = {"ref_area_label": table["ref_area"].map(lambda c: self.label("ref_area", c))}
        if "obs_status" in table:
            extra["obs_status_label"] = table["obs_status"].map(
                lambda c: self.label("obs_status", c)
            )
        table = table.assign(**extra)
        first = ["ref_area", "ref_area_label"]
        return table[first + [c for c in table.columns if c not in first]]

    def describe(self, code: str) -> dict[str, Any]:
        """What a measure is, in one place: for results, tool output and chart titles."""
        measure = self.measure(code)
        unit = measure.unit or next((u for u in self._units(code) if not u.endswith("_SUB")), None)
        return {
            "code": code,
            "name": self.name(code),
            "oecd_label": self.label("measure", code),
            "dimension": self.dimension(measure),
            "unit": measure.unit_label or (self.label("unit_measure", unit) if unit else None),
            "better": measure.better,
            "target": measure.target,
            "threshold": measure.threshold,
            "headline": measure.headline,
            "pooled": measure.pooled,
            "note": measure.note,
        }

    def coverage(self, code: str) -> dict[str, Any]:
        """Which OECD members, years and breakdowns a measure has data for."""
        totals = self.series(code)
        breakdowns = []
        for breakdown in BREAKDOWNS:
            try:
                self.series(code, breakdown)  # type: ignore[arg-type]
                breakdowns.append(breakdown)
            except AnalysisError:
                pass
        return {
            "countries": int(totals["ref_area"].nunique()),
            "first_year": int(totals["time_period"].min()) if not totals.empty else None,
            "last_year": int(totals["time_period"].max()) if not totals.empty else None,
            "breakdowns": breakdowns,
        }

    def find_measures(self, query: str, limit: int = 10) -> pd.DataFrame:
        """Measures matching a free-text query, best match first. Searches codes, How's Life?
        names, API labels, dimension names and notes, so "NEET", "deaths of despair" or "trust"
        all work."""
        words = [w for w in re.split(r"[^\w/]+", query.lower()) if w and w not in _FILLER]
        if not words:
            raise AnalysisError("Give at least one word to search for.")
        hits = []
        for code, measure in self.measures.items():
            name = (measure.name or "").lower()
            text = " ".join(
                [code.lower(), name, self.label("measure", code).lower(),
                 self.dimension(measure).lower(), (measure.note or "").lower()]
            )  # fmt: skip
            score = sum(w in text for w in words) + sum(w in name for w in words)
            if query.lower() == code.lower():
                score += 10
            if score:
                hits.append((score, code))
        hits.sort(key=lambda hit: (-hit[0], _code_order(hit[1])))
        return pd.DataFrame(
            [
                {
                    "code": code,
                    "name": self.name(code),
                    "dimension": self.dimension(self.measures[code]),
                    "better": self.measures[code].better,
                    "headline": self.measures[code].headline,
                }
                for _, code in hits[:limit]
            ],
            columns=["code", "name", "dimension", "better", "headline"],
        )

    def _units(self, code: str) -> list[str]:
        return list(
            self.observations.loc[self.observations["measure"] == code, "unit_measure"].unique()
        )


def _code_order(code: str) -> tuple[int, int, str]:
    dimension, number, *suffix = code.split("_")
    return int(dimension), int(number), "".join(suffix)
