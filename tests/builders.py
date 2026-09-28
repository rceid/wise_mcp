"""Small hand-built datasets for the analysis tests, so every expected answer can be worked out on
paper. Real OECD member codes are used because OECD averages depend on membership."""

import pandas as pd

from wise_mcp.analysis import WellbeingData

DIMENSIONS = {
    1: "Income and wealth", 5: "Health", 10: "Safety", 11: "Subjective well-being",
    12: "Natural capital",
}  # fmt: skip


def obs(
    ref_area: str,
    measure: str,
    year: int,
    value: float,
    status: str = "A",
    unit: str = "PT",
    sex: str = "_T",
    age: str = "_T",
    education_lev: str = "_T",
) -> dict:
    return {
        "ref_area": ref_area,
        "measure": measure,
        "unit_measure": unit,
        "age": age,
        "sex": sex,
        "education_lev": education_lev,
        "domain": f"HSL_{measure.split('_')[0]}",
        "time_period": year,
        "obs_value": float(value),
        "obs_status": status,
        "unit_mult": 0,
        "decimals": 2,
        "base_per": None,
    }


def series(measure: str, values: dict[str, dict[int, float]], **kwargs) -> list[dict]:
    """Rows from {country: {year: value}}."""
    return [
        obs(country, measure, year, value, **kwargs)
        for country, by_year in values.items()
        for year, value in by_year.items()
    ]


def make_data(rows: list[dict], measures: dict) -> WellbeingData:
    frame = pd.DataFrame(rows)
    frame["time_period"] = frame["time_period"].astype("int64")
    labels = {
        "ref_area": {code: f"Country {code}" for code in frame["ref_area"].unique()},
        "measure": {code: f"API label for {code}" for code in measures},
        "obs_status": {"A": "Normal value", "B": "Time series break", "E": "Estimated value"},
        "domain": {f"HSL_{n}": name for n, name in DIMENSIONS.items()},
        "sex": {"_T": "Total", "F": "Female", "M": "Male"},
        "age": {"_T": "Total", "YOUNG": "Young", "MID": "Middle-aged", "OLD": "Old"},
        "education_lev": {"_T": "Total", "ISCED11_1": "Primary", "ISCED11_2_3": "Secondary",
                          "ISCED11_5T8": "Tertiary"},
        "unit_measure": {"PT": "Percentage", "T_CO2E_PS": "Tonnes CO2e", "T_CO2_PS": "Tonnes CO2"},
    }  # fmt: skip
    return WellbeingData(observations=frame, labels=labels, measures=measures)
