"""Export How's Life? data for the R charts in this folder.

Uses wise_mcp's own analysis, so values, years and the member list follow the How's Life? 2024
method: OECD members only, national totals only.

    uv run python r/export_data.py

Writes:
    data/life_satisfaction.csv       each member's latest life satisfaction (circular barplot)
    data/income_life_expectancy.csv  household income and life expectancy by year (animation)
"""

from pathlib import Path

import pandas as pd

from wise_mcp.analysis import WellbeingData, compare_countries
from wise_mcp.store import DataStore

DATA = Path(__file__).parent / "data"
EXCLUDE = {"ISR"}  # not shown in these charts
FIRST_YEAR, LAST_YEAR = 2004, 2023  # the years both series cover for 30+ members

data = WellbeingData.from_store(DataStore())


def country(code: str) -> str:
    return data.label("ref_area", code)


# Life satisfaction (11_1, 0-10 scale): each member's latest year
satisfaction = compare_countries(data, "11_1").table
satisfaction = satisfaction.rename(
    columns={"ref_area": "iso3", "ref_area_label": "country", "time_period": "year",
             "obs_value": "value", "obs_status_label": "status"}
)[["iso3", "country", "year", "value", "status"]]  # fmt: skip
satisfaction = satisfaction[~satisfaction["iso3"].isin(EXCLUDE)]
satisfaction["value"] = satisfaction["value"].round(3)
satisfaction.to_csv(DATA / "life_satisfaction.csv", index=False)
print(f"life satisfaction: {len(satisfaction)} countries")


# Household income (1_1, USD per person, PPP) and life expectancy (5_1, years), by year
def yearly(code: str, name: str) -> pd.DataFrame:
    series = data.series(code)  # members' national totals
    return series.rename(columns={"ref_area": "iso3", "time_period": "year", "obs_value": name})[
        ["iso3", "year", name]
    ]


panel = yearly("1_1", "income").merge(yearly("5_1", "life_expectancy"), on=["iso3", "year"])
panel = panel[panel["year"].between(FIRST_YEAR, LAST_YEAR) & ~panel["iso3"].isin(EXCLUDE)]
panel.insert(1, "country", panel["iso3"].map(country))
panel = panel.sort_values(["iso3", "year"])
panel["income"] = panel["income"].round(0).astype(int)
panel["life_expectancy"] = panel["life_expectancy"].round(2)
panel.to_csv(DATA / "income_life_expectancy.csv", index=False)
print(f"income and life expectancy: {panel['iso3'].nunique()} countries, {len(panel)} rows")
