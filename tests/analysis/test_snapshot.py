import pytest
from builders import make_data, obs, series

from wise_mcp.analysis import AnalysisError, OecdAverage, compare_countries, latest, oecd_average
from wise_mcp.catalog import Measure

LIFE_SATISFACTION = Measure("11_1", "higher", threshold=0.2)


@pytest.fixture
def data():
    rows = series(
        "11_1",
        {
            "FRA": {2023: 7.0, 2024: 7.2},
            "DEU": {2025: 7.5},
            "MEX": {2021: 8.0},  # older latest year
            "BRA": {2024: 9.0},  # partner country, not an OECD member
            "OECD": {2024: 1.0},  # published aggregate row: never a country
        },
    )
    rows[1]["obs_status"] = "E"  # FRA 2024 is an estimate
    return make_data(rows, {"11_1": LIFE_SATISFACTION})


class TestLatest:
    def test_each_country_most_recent_value(self, data):
        table = latest(data, "11_1").set_index("ref_area")
        assert table["time_period"].to_dict() == {
            "BRA": 2024,
            "DEU": 2025,
            "FRA": 2024,
            "MEX": 2021,
        }
        assert table.loc["FRA", "obs_value"] == 7.2

    def test_specific_year(self, data):
        assert latest(data, "11_1", year=2023)["ref_area"].tolist() == ["FRA"]

    def test_labels_and_membership(self, data):
        table = latest(data, "11_1").set_index("ref_area")
        assert table.loc["FRA", "ref_area_label"] == "Country FRA"
        assert table.loc["FRA", "obs_status_label"] == "Estimated value"
        assert not table.loc["BRA", "oecd_member"]


class TestOecdAverage:
    def test_simple_mean_of_members_only(self, data):
        average = oecd_average(latest(data, "11_1"))
        assert average.value == pytest.approx((7.2 + 7.5 + 8.0) / 3)  # no BRA, no OECD row
        assert (average.countries, average.years, average.label) == (3, "2021-2025", "OECD 3")

    def test_label_says_oecd_when_every_member_has_data(self):
        assert OecdAverage(7.0, 38, 2024, 2024).label == "OECD"
        assert OecdAverage(7.0, 38, 2024, 2024).years == "2024"


class TestCompareCountries:
    def test_best_first_with_partners_ranked_but_not_averaged(self, data):
        result = compare_countries(data, "11_1")
        assert result.table["ref_area"].tolist() == ["BRA", "MEX", "DEU", "FRA"]
        assert result.table["rank"].tolist() == [1, 2, 3, 4]
        assert result.table["better_than_oecd"].tolist() == [True, True, False, False]
        assert result.oecd_average.countries == 3

    def test_lower_is_better_reverses_the_order(self):
        rows = series("10_1", {"FRA": {2024: 1.0}, "DEU": {2024: 0.8}, "ITA": {2024: 0.5}})
        data = make_data(rows, {"10_1": Measure("10_1", "lower")})
        assert compare_countries(data, "10_1").table["ref_area"].tolist() == ["ITA", "DEU", "FRA"]

    def test_target_ranks_by_distance_from_the_target(self):
        # With "lower is better", Luxembourg's negative wage gap would come first.
        rows = series("2_2", {"LUX": {2022: -8.7}, "FRA": {2024: 6.6}, "KOR": {2024: 29.0}})
        data = make_data(rows, {"2_2": Measure("2_2", "target", target=0)})
        assert compare_countries(data, "2_2").table["ref_area"].tolist() == ["FRA", "LUX", "KOR"]

    def test_ties_share_a_rank(self):
        rows = series("11_1", {"FIN": {2025: 7.8}, "DNK": {2025: 7.8}, "FRA": {2025: 7.0}})
        data = make_data(rows, {"11_1": LIFE_SATISFACTION})
        assert compare_countries(data, "11_1").table["rank"].tolist() == [1, 1, 3]

    def test_subset_keeps_the_full_oecd_average(self, data):
        result = compare_countries(data, "11_1", ["fra"])
        assert result.table["ref_area"].tolist() == ["FRA"]
        assert result.oecd_average.countries == 3

    def test_measure_description_travels_with_the_result(self, data):
        described = compare_countries(data, "11_1").measure
        assert (described["code"], described["better"]) == ("11_1", "higher")

    def test_unknown_or_missing_countries(self, data):
        with pytest.raises(AnalysisError, match="Unknown country"):
            compare_countries(data, "11_1", ["XXX"])
        with pytest.raises(AnalysisError, match="No data"):
            compare_countries(
                make_data([obs("FRA", "11_1", 2024, 7), obs("DEU", "5_1", 2024, 80)],
                          {"11_1": LIFE_SATISFACTION, "5_1": Measure("5_1", "higher")}),
                "11_1", ["DEU"],
            )  # fmt: skip


class TestCaveats:
    def test_differing_years_flags_and_partners(self, data):
        caveats = " ".join(compare_countries(data, "11_1").caveats)
        assert "from 2021 (MEX) to 2025" in caveats
        assert "FRA 2024 (estimated value)" in caveats
        assert "BRA is not OECD member(s)" in caveats

    def test_uncomparable_measures_are_listed_but_not_ranked(self):
        rows = series("12_4", {"CAN": {2016: 2_000_000.0}, "FRA": {2016: 0.0}})
        data = make_data(rows, {"12_4": Measure("12_4", "higher", comparable=False)})
        result = compare_countries(data, "12_4")
        assert result.table["rank"].isna().all()
        assert result.table["ref_area"].tolist() == ["CAN", "FRA"]  # alphabetical, not by size
        assert any("aren't ranked" in c for c in result.caveats)

    def test_dated_measures(self):
        rows = series("2_6", {"FRA": {2015: 30.0}}) + [obs("FRA", "11_1", 2025, 7.0)]
        data = make_data(rows, {"2_6": Measure("2_6", "lower"), "11_1": LIFE_SATISFACTION})
        assert "most recent data for this measure are from 2015" in " ".join(
            compare_countries(data, "2_6").caveats
        )
