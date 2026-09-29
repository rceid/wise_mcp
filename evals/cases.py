"""The eval questions: each answered by a naive analysis of the raw OECD data and by wise_mcp.

"Naive" is a reasonable first pass with pandas and no How's Life? know-how: filter the downloaded
data to the measure code and compute the obvious thing. It is what an analyst (or an LLM handed
the CSV) does before reading the report's Reader's Guide. Every naive answer below is a mistake
someone would plausibly make; the `pitfall` says what the report's method does differently.

Where How's Life? 2024 publishes the number, `published` holds it, so both answers can be
checked against the OECD's own figure.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from wise_mcp import analysis
from wise_mcp.analysis import AnalysisError, WellbeingData
from wise_mcp.analysis.headlines import headline_scores


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    naive: Callable[[pd.DataFrame, WellbeingData], str]
    wise: Callable[[WellbeingData], str]
    pitfall: str
    published: str | None = None  # the How's Life? 2024 figure, with its wording
    published_value: float | None = None  # ... as a number, to score both answers against


# --- Naive helpers: what a first pass with pandas does -----------------------------------------


def rows(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    """Every row for a measure code: all countries, all breakdowns, all units."""
    return raw[raw["measure"] == code]


def naive_latest(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    """The newest year in the data, every row in it."""
    r = rows(raw, code)
    return r[r["time_period"] == r["time_period"].max()]


def naive_country(raw: pd.DataFrame, code: str, country: str) -> pd.DataFrame:
    r = rows(raw, code)
    return r[r["ref_area"] == country].sort_values("time_period")


def fmt(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


# --- Wise helpers ------------------------------------------------------------------------------


def average_in(data: WellbeingData, code: str, year: int) -> str:
    avg = analysis.oecd_average(analysis.latest(data, code, year=year))
    if avg is None:
        raise AnalysisError(f"no {code} data for {year}")
    return f"{fmt(avg.value)} ({avg.label}, {year})"


def top(data: WellbeingData, code: str, n: int = 3, best: bool = True) -> str:
    table = analysis.compare_countries(data, code).table
    table = table.head(n) if best else table.tail(n).iloc[::-1]
    return ", ".join(f"{r.ref_area} {fmt(r.obs_value)} ({r.time_period})"
                     for r in table.itertuples())  # fmt: skip


def change(data: WellbeingData, code: str, country: str, since: str = "2010") -> str:
    result = analysis.trend(data, code, [country], since=since)
    r = result.changes.iloc[0]
    if pd.isna(r.end_year):
        return "insufficient data"
    flags = " (series break)" if r.series_break else ""
    return (f"{r.start_year} {fmt(r.start_value)} → {r.end_year} {fmt(r.end_value)}: "
            f"{r.assessment}{flags}")  # fmt: skip


# --- The cases ---------------------------------------------------------------------------------


def _naive_mean(code: str, year: int) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, _: WellbeingData) -> str:
        r = rows(raw, code)
        r = r[r["time_period"] == year]
        return (
            f"{fmt(r['obs_value'].mean())} (mean of {len(r)} rows, {r['ref_area'].nunique()} areas)"
        )

    return naive


def _naive_top(code: str, ascending: bool = False) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, _: WellbeingData) -> str:
        r = naive_latest(raw, code).sort_values("obs_value", ascending=ascending).head(3)
        year = int(r["time_period"].iloc[0])
        listed = ", ".join(f"{row.ref_area} {fmt(row.obs_value)}" for row in r.itertuples())
        return f"{listed} (all {year})"

    return naive


def _naive_lowest_latest(code: str) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, _: WellbeingData) -> str:
        r = rows(raw, code)
        r = r[(r["sex"] == "_T") & (r["age"] == "_T") & (r["education_lev"] == "_T")]
        r = r.sort_values("time_period").groupby("ref_area").tail(1).sort_values("obs_value")
        return ", ".join(
            f"{row.ref_area} {fmt(row.obs_value)} ({row.time_period})"
            for row in r.head(3).itertuples()
        )

    return naive


def _naive_first_last(code: str, country: str) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, _: WellbeingData) -> str:
        r = naive_country(raw, code, country)
        r = r[(r["sex"] == "_T") & (r["age"] == "_T") & (r["education_lev"] == "_T")]
        first, last = r.iloc[0], r.iloc[-1]
        d = last["obs_value"] - first["obs_value"]
        word = "improved" if d > 0 else "worsened"
        return (f"{first['time_period']} {fmt(first['obs_value'])} → {last['time_period']} "
                f"{fmt(last['obs_value'])}: {word} by {fmt(abs(d))}")  # fmt: skip

    return naive


def _latest_value(code: str, country: str) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, data: WellbeingData) -> str:
        r = naive_country(raw, code, country)
        r = r[(r["sex"] == "_T") & (r["age"] == "_T") & (r["education_lev"] == "_T")]
        last = r.iloc[-1]
        unit = data.label("unit_measure", last["unit_measure"])
        return f"{fmt(last['obs_value'])} {unit} ({last['time_period']})"

    return naive


def _naive_label(code: str, country: str) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, data: WellbeingData) -> str:
        return f"'{data.label('measure', code)}': {_latest_value(code, country)(raw, data)}"

    return naive


def _wise_named(code: str, country: str) -> Callable[[WellbeingData], str]:
    def wise(data: WellbeingData) -> str:
        return f"{data.name(code)}: {_wise_value(code, country)(data)}. {data.measure(code).note}"

    return wise


def _wise_value(code: str, country: str) -> Callable[[WellbeingData], str]:
    def wise(data: WellbeingData) -> str:
        r = analysis.compare_countries(data, code, [country]).table.iloc[0]
        return f"{fmt(r.obs_value)} {data.describe(code)['unit']} ({r.time_period})"

    return wise


def _naive_count(code: str) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, _: WellbeingData) -> str:
        r = naive_latest(raw, code)
        return (
            f"{fmt(r['obs_value'].mean())}, 'the OECD average' over {r['ref_area'].nunique()} areas"
        )

    return naive


def _wise_count(code: str) -> Callable[[WellbeingData], str]:
    def wise(data: WellbeingData) -> str:
        avg = analysis.compare_countries(data, code).oecd_average
        return f"{fmt(avg.value)} ({avg.label}, latest years {avg.years})"

    return wise


def _naive_gender_gap_safe(raw: pd.DataFrame, _: WellbeingData) -> str:
    r = naive_country(raw, "10_2", "FRA")
    r = r[(r["sex"] == "_T") & (r["age"] == "_T") & (r["education_lev"] == "_T")].iloc[-1]
    return (
        f"No 'gender gap' measure in the data; the total is {fmt(r['obs_value'])}% "
        f"({r['time_period']}), so no answer"
    )


def _wise_gender_gap_safe(data: WellbeingData) -> str:
    profile = analysis.country_profile(data, "FRA").indicators.set_index("code")
    r = profile.loc["10_2"]
    return (
        f"{fmt(r.obs_value)} points, men minus women ({r.time_period}); rank {r['rank']}/{r.out_of}"
    )


def _naive_complement(raw: pd.DataFrame, _: WellbeingData) -> str:
    r = naive_country(raw, "7_1", "FRA")
    r = r[(r["sex"] == "_T") & (r["age"] == "_T") & (r["education_lev"] == "_T")].iloc[-1]
    return f"100 − {fmt(r['obs_value'])} = {fmt(100 - r['obs_value'])}% ({r['time_period']})"


def _naive_carbon(raw: pd.DataFrame, _: WellbeingData) -> str:
    r = naive_country(raw, "12_9", "FRA")
    r = r[r["time_period"] == 2018]
    return f"{fmt(r['obs_value'].mean())} (mean of {len(r)} rows: {sorted(r['unit_measure'])})"


def _wise_carbon(data: WellbeingData) -> str:
    table = analysis.latest(data, "12_9", year=2018)
    r = table[table["ref_area"] == "FRA"].iloc[0]
    return f"{fmt(r.obs_value)} {data.describe('12_9')['unit']} (2018; CO2-equivalent by default)"


def _naive_rank(code: str, country: str) -> Callable[[pd.DataFrame, WellbeingData], str]:
    def naive(raw: pd.DataFrame, _: WellbeingData) -> str:
        r = naive_latest(raw, code)
        r = r[(r["sex"] == "_T") & (r["age"] == "_T") & (r["education_lev"] == "_T")]
        order = r.sort_values("obs_value", ascending=False)["ref_area"].tolist()
        others = [a for a in ("OECD", "BRA", "ROU", "BGR", "ARG") if a in order]
        return (f"rank {order.index(country) + 1} of {len(order)} "
                f"(the list includes {', '.join(others)})")  # fmt: skip

    return naive


def _wise_rank(code: str, country: str) -> Callable[[WellbeingData], str]:
    def wise(data: WellbeingData) -> str:
        result = analysis.compare_countries(data, code, [country])
        r = result.table.iloc[0]
        return f"rank {r['rank']} of {result.oecd_average.countries} OECD members ({r.time_period})"

    return wise


def _naive_stale(raw: pd.DataFrame, _: WellbeingData) -> str:
    r = naive_country(raw, "2_6", "FRA")
    last = r[(r["sex"] == "_T") & (r["age"] == "_T") & (r["education_lev"] == "_T")].iloc[-1]
    return f"{fmt(last['obs_value'])}% of employees, 'latest'"


def _wise_stale(data: WellbeingData) -> str:
    result = analysis.compare_countries(data, "2_6", ["FRA"])
    r = result.table.iloc[0]
    stale = next((c for c in result.caveats if "most recent data" in c), "")
    return f"{fmt(r.obs_value)}% ({r.time_period}). {stale}"


def _wise_index_rank(data: WellbeingData) -> str:
    scores = analysis.wellbeing_index(data).scores.set_index("ref_area")
    r = scores.loc["FRA"]
    return (
        f"rank {r['rank']} of {len(scores)} on Better Life 36 (current well-being), "
        f"score {fmt(r.score)}"
    )


def _naive_index_rank(raw: pd.DataFrame, _: WellbeingData) -> str:
    return (
        "No overall score in the data: it needs the 36 headline indicators, their direction and "
        "the report's rescaling, none of which is in the CSV"
    )


def _wise_headline_count(data: WellbeingData) -> str:
    scores = headline_scores(data, "current")
    return f"{scores['code'].nunique()} current-well-being headline indicators with data after 2019"


CASES: list[Case] = [
    Case(
        "avg-life-expectancy",
        "What was the OECD average life expectancy at birth in 2022?",
        _naive_mean("5_1", 2022),
        lambda d: average_in(d, "5_1", 2022),
        "The naive mean includes partner countries and the women/men rows. How's Life? averages "
        "the 38 members' totals only.",
        published='80.7 years ("A newborn in 2022 could expect to live 80.7 years")',
        published_value=80.7,
    ),
    Case(
        "avg-employment",
        "What was the OECD average employment rate in 2023?",
        _naive_mean("2_1", 2023),
        lambda d: average_in(d, "2_1", 2023),
        "Breakdown rows (by sex, age, education) pull the naive mean around.",
        published='78% ("In 2023, 78% of those aged 25-64 were employed")',
        published_value=78.0,
    ),
    Case(
        "avg-housing",
        "How much income did OECD households have left after housing costs in 2022?",
        _naive_mean("3_2", 2022),
        lambda d: average_in(d, "3_2", 2022),
        "Same mixing of partners and breakdowns.",
        published='79% ("79% of their disposable income left after housing costs")',
        published_value=79.0,
    ),
    Case(
        "avg-long-hours",
        "What share of employees worked very long hours in 2022, OECD-wide?",
        _naive_mean("2_7", 2022),
        lambda d: average_in(d, "2_7", 2022),
        "Same mixing of partners and breakdowns.",
        published='about 7.1% ("Around one in 14 employees ... worked long hours")',
        published_value=100 / 14,
    ),
    Case(
        "top-life-satisfaction",
        "Which three OECD countries have the highest life satisfaction?",
        _naive_top("11_1"),
        lambda d: top(d, "11_1"),
        "The newest year covers only a few countries, and it mixes breakdown rows and partners. "
        "Each country's latest year, members only, gives a different top three.",
    ),
    Case(
        "lowest-homicides",
        "Which countries have the lowest homicide rates?",
        _naive_top("10_1", ascending=False),
        lambda d: top(d, "10_1"),
        "Sorting high-to-low, as for most measures, lists the highest homicide rates as the "
        "'best'. Nothing in the data says lower is better.",
    ),
    Case(
        "wage-gap-best",
        "Which country has the smallest gender wage gap?",
        _naive_lowest_latest("2_2"),
        lambda d: top(d, "2_2", n=3),
        "Lowest-first puts a negative gap (women paid more) first. The goal is no gap, so "
        "wise_mcp ranks by distance from 0.",
    ),
    Case(
        "france-life-sat-trend",
        "Has life satisfaction in France improved since 2010?",
        _naive_first_last("11_1", "FRA"),
        lambda d: change(d, "11_1", "FRA"),
        "Any change counts as 'improved' naively. How's Life? needs at least 0.2 points to call "
        "it improving, and compares around 2010 with the latest year.",
    ),
    Case(
        "france-trust-trend",
        "Has trust in national government in France changed since 2010?",
        _naive_first_last("14_3", "FRA"),
        lambda d: change(d, "14_3", "FRA"),
        "The first year in the data is 2006, not 2010, and each value is repeated for every year "
        "of a 3-year period: 2025 is the 2023-25 figure.",
    ),
    Case(
        "france-trust-others-trend",
        "Has trust in others fallen in France since 2013?",
        _naive_first_last("14_1", "FRA"),
        lambda d: change(d, "14_1", "FRA", since="2013"),
        "The series has breaks (method changes) in 2013, 2021 and 2022, so part of the fall may "
        "not be real. The naive answer can't tell.",
    ),
    Case(
        "gender-gap-safe",
        "How big is the gender gap in feeling safe at night in France?",
        _naive_gender_gap_safe,
        _wise_gender_gap_safe,
        "The headline indicator is the gap between men and women; it isn't in the data at all "
        "and has to be computed from the breakdown by sex.",
    ),
    Case(
        "lack-social-support",
        "What share of people in France lack social support?",
        _naive_complement,
        _wise_value("7_1_DEP", "FRA"),
        "'Lack of social support' isn't 100 minus 'social support': some answers ('don't know') "
        "fall in neither. It has its own measure (7_1_DEP).",
    ),
    Case(
        "emissions-unit",
        "How much greenhouse gas does France emit per person?",
        _latest_value("12_8", "FRA"),
        _wise_value("12_8", "FRA"),
        "The OECD labels the unit kilograms, but the values are tonnes: read at face value, "
        "France emits 1,000 times less than it does.",
    ),
    Case(
        "carbon-footprint-units",
        "What was France's carbon footprint per person in 2018?",
        _naive_carbon,
        _wise_carbon,
        "The code holds two series (CO2 and CO2-equivalent), so a naive mean averages two "
        "different units.",
    ),
    Case(
        "s80-s20-label",
        "What does measure 1_2 show for France?",
        _naive_label("1_2", "FRA"),
        _wise_named("1_2", "FRA"),
        "The API calls it 'Top average household disposable income quintile'. It is the S80/S20 "
        "ratio: the top 20%'s income divided by the bottom 20%'s.",
    ),
    Case(
        "oecd-count",
        "What is the OECD average trust in others?",
        _naive_count("14_1"),
        _wise_count("14_1"),
        "How's Life? averages members with data, each at its latest year, and says how many "
        "('OECD 30'). The naive mean is over whoever has the newest year, partner countries "
        "(Bulgaria, Croatia, Romania) included.",
    ),
    Case(
        "oecd-row",
        "Where does France rank on renewable energy supply?",
        _naive_rank("12_10", "FRA"),
        _wise_rank("12_10", "FRA"),
        "Future well-being includes a row for 'OECD' itself, which a naive ranking counts as a "
        "country, and partner countries sit in the same table.",
    ),
    Case(
        "stale-indicator",
        "What share of employees in France face job strain?",
        _naive_stale,
        _wise_stale,
        "Job strain stopped in 2015. The naive 'latest' value is a decade old with no warning.",
    ),
    Case(
        "overall-rank",
        "Where does France rank on overall well-being?",
        _naive_index_rank,
        _wise_index_rank,
        "The report's overall picture rescales the 36 headline indicators (which ones, and "
        "which direction is better, are only in the report) and averages by dimension.",
    ),
    Case(
        "headline-coverage",
        "How many of the headline indicators have recent data?",
        lambda raw, d: "Can't tell: which measures are headlines is only in the report",
        _wise_headline_count,
        "Which 36 of the 103 measures are headline indicators is listed only in the report.",
    ),
]


def answer(fn: Callable[..., str], *args: object) -> str:
    """Run one side of a case, reporting a missing measure instead of failing the whole run."""
    try:
        return fn(*args)
    except (AnalysisError, IndexError, KeyError, ValueError) as exc:
        return f"(no answer: {exc})"
