import pytest
from builders import make_data, obs

from wise_mcp.analysis import AnalysisError, group_gaps
from wise_mcp.catalog import Measure

FEELING_SAFE = Measure("10_2", "higher", threshold=3)
HOMICIDES = Measure("10_1", "lower", threshold=0.3)


def by_sex(code, country, year, total, female, male):
    return [
        obs(country, code, year, total),
        obs(country, code, year, female, sex="F", unit="PT_SUB"),
        obs(country, code, year, male, sex="M", unit="PT_SUB"),
    ]


class TestScores:
    def test_higher_is_better(self):
        data = make_data(by_sex("10_2", "FRA", 2024, 70, 60, 80), {"10_2": FEELING_SAFE})
        result = group_gaps(data, "10_2", "sex")
        scores = result.groups.set_index("sex")["score"]
        assert scores["F"] == pytest.approx(60 / 70)
        assert scores["M"] == pytest.approx(80 / 70)
        summary = result.summary.iloc[0]
        assert summary["better_off"] == "Male"
        assert summary["F_vs_M"] == pytest.approx(0.75)  # women's score is 3/4 of men's

    def test_lower_is_better_flips_the_ratio(self):
        # Homicides: men 5 per 100 000, women 1. Women are 3 times less likely than average.
        data = make_data(by_sex("10_1", "FRA", 2021, 3, 1, 5), {"10_1": HOMICIDES})
        result = group_gaps(data, "10_1", "sex")
        assert result.groups.set_index("sex")["score"]["F"] == pytest.approx(3.0)
        assert result.summary.iloc[0]["better_off"] == "Female"

    def test_within_003_of_parity_is_no_clear_difference(self):
        data = make_data(by_sex("10_2", "FRA", 2024, 70, 69, 71), {"10_2": FEELING_SAFE})
        assert group_gaps(data, "10_2").summary.iloc[0]["better_off"] == "no clear difference"

    def test_zero_values_give_no_ratio_instead_of_infinity(self):
        data = make_data(by_sex("10_1", "ISL", 2021, 0.5, 0.0, 1.0), {"10_1": HOMICIDES})
        result = group_gaps(data, "10_1")
        assert result.groups["score"].isna().any()
        assert result.summary.iloc[0]["better_off"] == "not computable"
        assert any("value of 0 in ISL" in c for c in result.caveats)


def test_uses_the_latest_year_with_every_group():
    rows = by_sex("10_2", "FRA", 2023, 70, 60, 80) + [
        obs("FRA", "10_2", 2024, 71),
        obs("FRA", "10_2", 2024, 62, sex="F", unit="PT_SUB"),  # no men's value for 2024
    ]
    result = group_gaps(make_data(rows, {"10_2": FEELING_SAFE}), "10_2")
    assert result.summary.iloc[0]["time_period"] == 2023


def test_age_compares_younger_people_with_the_middle_aged_and_older():
    rows = [obs("FRA", "10_2", 2024, 70)] + [
        obs("FRA", "10_2", 2024, value, age=age, unit="PT_SUB")
        for age, value in [("YOUNG", 77), ("MID", 70), ("OLD", 63)]
    ]
    result = group_gaps(make_data(rows, {"10_2": FEELING_SAFE}), "10_2", "age")
    summary = result.summary.iloc[0]
    assert summary["YOUNG_vs_MID"] == pytest.approx(1.1)
    assert summary["YOUNG_vs_OLD"] == pytest.approx(77 / 63)
    assert result.groups["age"].tolist() == ["YOUNG", "MID", "OLD"]  # natural order


def test_oecd_average_covers_every_member_even_for_one_country():
    rows = (
        by_sex("10_2", "FRA", 2024, 70, 60, 80)
        + by_sex("10_2", "DEU", 2024, 80, 76, 84)
        + by_sex("10_2", "BRA", 2024, 40, 30, 50)  # partner: excluded
    )
    result = group_gaps(make_data(rows, {"10_2": FEELING_SAFE}), "10_2", countries=["FRA"])
    assert result.summary["ref_area"].tolist() == ["FRA"]
    assert result.oecd["countries"] == 2
    assert result.oecd["values"] == {"Female": 68.0, "Male": 82.0}


def test_questions_the_data_cannot_answer():
    wage_gap = Measure("2_2", "target", target=0)
    data = make_data(
        by_sex("10_2", "FRA", 2024, 70, 60, 80) + [obs("FRA", "2_2", 2024, 12)],
        {"10_2": FEELING_SAFE, "2_2": wage_gap},
    )
    with pytest.raises(AnalysisError, match="itself a gap"):
        group_gaps(data, "2_2")
    with pytest.raises(AnalysisError, match="no breakdown by education"):
        group_gaps(data, "10_2", "education")
    with pytest.raises(AnalysisError, match="must be one of"):
        group_gaps(data, "10_2", "income")  # type: ignore[arg-type]
