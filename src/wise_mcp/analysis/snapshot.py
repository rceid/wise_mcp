"""Where countries stand today: each country's latest value, the OECD average, and rankings."""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from wise_mcp.analysis.data import AnalysisError, WellbeingData, goodness, pooled_caveat
from wise_mcp.catalog import OECD_MEMBERS, Measure

# Flag a measure as dated when its newest data are this many years older than the newest data in
# the whole database.
STALE_AFTER_YEARS = 5


@dataclass(frozen=True)
class OecdAverage:
    """A simple mean over OECD members with data, as How's Life? computes it."""

    value: float
    countries: int
    first_year: int
    last_year: int

    @property
    def label(self) -> str:
        """ "OECD" when every member has data, otherwise e.g. "OECD 33", as in How's Life?."""
        return "OECD" if self.countries == len(OECD_MEMBERS) else f"OECD {self.countries}"

    @property
    def years(self) -> str:
        if self.first_year == self.last_year:
            return str(self.first_year)
        return f"{self.first_year}-{self.last_year}"


@dataclass(frozen=True)
class Comparison:
    measure: dict[str, Any]
    table: pd.DataFrame  # one row per country, best first
    oecd_average: OecdAverage | None
    caveats: list[str]


def latest(data: WellbeingData, code: str, year: int | None = None) -> pd.DataFrame:
    """Each country's most recent value (or its value in `year`), with labels."""
    series = data.series(code)
    if year is not None:
        rows = series[series["time_period"] == year]
    else:
        rows = series.groupby("ref_area").tail(1)  # series is sorted by country, then year
    return data.with_labels(rows.reset_index(drop=True))


def oecd_average(table: pd.DataFrame) -> OecdAverage | None:
    """Simple mean over a table from `latest`, which only ever holds OECD members."""
    if table.empty:
        return None
    return OecdAverage(
        value=float(table["obs_value"].mean()),
        countries=len(table),
        first_year=int(table["time_period"].min()),
        last_year=int(table["time_period"].max()),
    )


def compare_countries(
    data: WellbeingData, code: str, countries: list[str] | None = None
) -> Comparison:
    """Rank countries on one measure using each one's latest value, best first. Ranks and the
    OECD average always cover every member with data, even when only a few countries are
    compared: France is 10th of 38, not 1st of the countries asked about."""
    measure = data.measure(code)
    countries = data.check_countries(countries)
    everyone = latest(data, code)
    average = oecd_average(everyone)

    score = goodness(measure, everyone["obs_value"])
    table = everyone.assign(
        rank=score.rank(ascending=False, method="min").astype("Int64")
        if measure.comparable
        else pd.array([pd.NA] * len(everyone), dtype="Int64"),
        better_than_oecd=(score > goodness(measure, average.value) if average else pd.NA),
    )
    if measure.comparable:
        table = table.loc[score.sort_values(ascending=False).index]
    else:
        table = table.sort_values("ref_area_label")
    if countries is not None:
        table = table[table["ref_area"].isin(countries)]
    if table.empty:
        raise AnalysisError(f"No data for {data.name(code)} ({code}) in {countries}.")
    table = table.reset_index(drop=True)

    return Comparison(
        measure=data.describe(code),
        table=table,
        oecd_average=average,
        caveats=snapshot_caveats(data, measure, table),
    )


def snapshot_caveats(data: WellbeingData, measure: Measure, table: pd.DataFrame) -> list[str]:
    """Plain-language warnings about comparing the values in a table from `latest`."""
    caveats = []
    first, last = int(table["time_period"].min()), int(table["time_period"].max())
    if first != last:
        oldest = table[table["time_period"] == first]["ref_area"].tolist()
        caveats.append(
            f"Latest years differ, from {first} ({', '.join(oldest[:5])}) to {last}: "
            "some values being compared are several years apart."
        )

    newest_in_database = int(data.observations["time_period"].max())
    if last <= newest_in_database - STALE_AFTER_YEARS:
        caveats.append(f"The most recent data for this measure are from {last}.")

    flagged = table[table["obs_status"] != "A"]
    if not flagged.empty:
        listed = ", ".join(
            f"{row.ref_area} {row.time_period} ({row.obs_status_label.lower()})"
            for row in flagged.head(6).itertuples()
        )
        more = f" and {len(flagged) - 6} more" if len(flagged) > 6 else ""
        caveats.append(f"Flagged values: {listed}{more}.")

    if measure.pooled:
        row = table.iloc[0]
        caveats.append(
            pooled_caveat(
                [data.name(measure.code)], data.series(measure.code), row["ref_area"],
                [int(row["time_period"])],
            )
        )  # fmt: skip

    if not measure.comparable:
        caveats.append(
            "Values can't be compared across countries (e.g. absolute areas), so they "
            "aren't ranked."
        )
    return caveats
