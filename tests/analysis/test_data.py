import pandas as pd
import pytest
from builders import make_data, obs, series

from wise_mcp.analysis import AnalysisError, WellbeingData, goodness
from wise_mcp.catalog import Measure, load_measures

LIFE_SATISFACTION = Measure("11_1", "higher", threshold=0.2)


class TestSeries:
    def test_population_totals_only(self):
        data = make_data(
            [
                obs("FRA", "11_1", 2024, 7.1),
                obs("FRA", "11_1", 2024, 7.0, sex="F"),
                obs("FRA", "11_1", 2024, 7.2, age="YOUNG"),
                obs("OECD", "11_1", 2024, 6.9),  # a published aggregate, not a country
                obs("BRA", "11_1", 2024, 6.4),  # a partner country, not an OECD member
            ],
            {"11_1": LIFE_SATISFACTION},
        )
        assert data.series("11_1")[["ref_area", "obs_value"]].values.tolist() == [["FRA", 7.1]]

    def test_breakdown_returns_each_group(self):
        data = make_data(
            [
                obs("FRA", "11_1", 2024, 7.1),
                obs("FRA", "11_1", 2024, 7.0, sex="F", unit="PT_SUB"),
                obs("FRA", "11_1", 2024, 7.2, sex="M", unit="PT_SUB"),
                obs("FRA", "11_1", 2024, 6.8, sex="F", age="YOUNG", unit="PT_SUB"),  # crossed
            ],
            {"11_1": LIFE_SATISFACTION},
        )
        by_sex = data.series("11_1", "sex")
        assert by_sex[["sex", "obs_value"]].values.tolist() == [["F", 7.0], ["M", 7.2]]

    def test_missing_breakdown_is_explained(self):
        data = make_data([obs("FRA", "11_1", 2024, 7.1)], {"11_1": LIFE_SATISFACTION})
        with pytest.raises(AnalysisError, match="no breakdown by age"):
            data.series("11_1", "age")

    def test_default_unit_is_used_when_there_are_two(self):
        carbon = Measure("12_9", "lower", unit="T_CO2E_PS")
        rows = [obs("FRA", "12_9", 2020, 6.0, unit="T_CO2E_PS"),
                obs("FRA", "12_9", 2020, 5.0, unit="T_CO2_PS")]  # fmt: skip
        data = make_data(rows, {"12_9": carbon})
        assert data.series("12_9")["obs_value"].tolist() == [6.0]

        without_default = make_data(rows, {"12_9": Measure("12_9", "lower")})
        with pytest.raises(AnalysisError, match="several units"):
            without_default.series("12_9")

    def test_rows_are_sorted_by_country_then_year(self):
        rows = series("11_1", {"FRA": {2024: 7.0, 2020: 6.5}, "DEU": {2022: 7.1}})
        result = make_data(rows, {"11_1": LIFE_SATISFACTION}).series("11_1")
        assert result[["ref_area", "time_period"]].values.tolist() == [
            ["DEU", 2022], ["FRA", 2020], ["FRA", 2024]
        ]  # fmt: skip


def test_unknown_measure_points_to_search():
    data = make_data([obs("FRA", "11_1", 2024, 7.1)], {"11_1": LIFE_SATISFACTION})
    with pytest.raises(AnalysisError, match="find_measures"):
        data.series("99_9")


def test_country_codes_are_checked_and_upper_cased():
    data = make_data([obs("FRA", "11_1", 2024, 7.1)], {"11_1": LIFE_SATISFACTION})
    assert data.check_countries(["fra"]) == ["FRA"]
    with pytest.raises(AnalysisError, match="Unknown country"):
        data.check_countries(["France"])


@pytest.mark.parametrize(
    ("measure", "values", "expected"),
    [
        (Measure("x_1", "higher"), [1, 3], [1, 3]),
        (Measure("x_1", "lower"), [1, 3], [-1, -3]),
        (Measure("x_1", "target", target=0), [-8, 6], [-8, -6]),  # -8 is further from 0
        (Measure("x_1", "target", target=50), [48, 51], [-2, -1]),
    ],
)
def test_goodness_puts_every_measure_on_a_higher_is_better_scale(measure, values, expected):
    assert goodness(measure, pd.Series(values)).tolist() == expected


@pytest.fixture(scope="module")
def catalogue():
    # The real catalogue, so these tests also check the How's Life? names in measures.yaml.
    domains = {f"HSL_{n}": f"Dimension {n}" for n in range(1, 16)}
    return WellbeingData(pd.DataFrame(), {"domain": domains}, load_measures())


class TestFindMeasures:
    @pytest.mark.parametrize(
        ("query", "code"),
        [("NEET", "2_4"), ("deaths of despair", "5_3"), ("S80/S20", "1_2"), ("11_1", "11_1")],
    )
    def test_best_match_first(self, catalogue, query, code):
        assert catalogue.find_measures(query)["code"].iloc[0] == code

    def test_filler_words_do_not_match(self, catalogue):
        codes = catalogue.find_measures("deaths of despair")["code"].tolist()
        assert codes == ["5_3", "10_3"]  # deaths of despair, then road deaths

    def test_empty_query(self, catalogue):
        with pytest.raises(AnalysisError, match="at least one word"):
            catalogue.find_measures("of the")
