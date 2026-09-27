"""Headline scores, the Better Life 36 index and country profiles on a tiny dataset: three OECD
members (FRA, DEU, ITA) and one partner country (BRA), which the analysis leaves out. Expected
scores are worked out in the comments."""

import pytest
from builders import make_data, obs, series

from wise_mcp.analysis import AnalysisError, country_profile, headline_scores, wellbeing_index
from wise_mcp.analysis.headlines import _tier
from wise_mcp.catalog import Measure

MEASURES = {
    "1_1": Measure("1_1", "higher", headline="average", name="Household income"),
    "1_2": Measure("1_2", "lower", headline="vertical_inequality", name="S80/S20"),
    "5_1": Measure("5_1", "higher", headline="average", name="Life expectancy"),
    "10_2": Measure("10_2", "higher", headline="horizontal_inequality", name="Feeling safe"),
    "11_1": Measure("11_1", "higher", name="Life satisfaction"),  # not a headline
    "12_8": Measure("12_8", "lower", headline="risk_factor", name="Emissions"),
}


def feeling_safe(country, female, male):
    return [
        obs(country, "10_2", 2022, (female + male) / 2),
        obs(country, "10_2", 2022, female, sex="F", unit="PT_SUB"),
        obs(country, "10_2", 2022, male, sex="M", unit="PT_SUB"),
    ]


@pytest.fixture
def data():
    rows = (
        # Income, higher is better: ITA 30 (worst) -> 0, FRA 40 -> 0.5, DEU 50 (best) -> 1
        series("1_1", {"FRA": {2022: 40}, "DEU": {2022: 50}, "ITA": {2022: 30}, "BRA": {2022: 10}})
        # S80/S20, lower is better: FRA 4 -> 1, DEU 5 -> 0.5, ITA 6 -> 0
        + series("1_2", {"FRA": {2022: 4}, "DEU": {2022: 5}, "ITA": {2022: 6}})
        # Life expectancy: ITA only has 2018, which is before the cut-off: FRA 1, DEU 0
        + series("5_1", {"FRA": {2022: 82}, "DEU": {2022: 80}, "ITA": {2018: 84}})
        # Gender gap in feeling safe (men minus women), target 0: FRA 20 -> 0, DEU 5 -> 15/18,
        # ITA 2 -> 1
        + feeling_safe("FRA", 60, 80)
        + feeling_safe("DEU", 75, 80)
        + feeling_safe("ITA", 70, 72)
        + series("11_1", {"FRA": {2022: 7}})
        # Emissions, lower is better: FRA 5 -> 1, ITA 6 -> 2/3, DEU 8 -> 0
        + series("12_8", {"FRA": {2022: 5}, "DEU": {2022: 8}, "ITA": {2022: 6}})
    )
    return make_data(rows, MEASURES)


class TestHeadlineScores:
    def test_rescaled_from_worst_member_to_best(self, data):
        scores = headline_scores(data).set_index(["code", "ref_area"])["score"]
        assert scores["1_1"].to_dict() == pytest.approx({"FRA": 0.5, "DEU": 1.0, "ITA": 0.0})
        assert scores["1_2"].to_dict() == pytest.approx({"FRA": 1.0, "DEU": 0.5, "ITA": 0.0})

    def test_partner_countries_are_left_out(self, data):
        assert "BRA" not in set(headline_scores(data)["ref_area"])

    def test_values_from_2019_or_earlier_are_left_out(self, data):
        life_expectancy = headline_scores(data).query("code == '5_1'")
        assert set(life_expectancy["ref_area"]) == {"FRA", "DEU"}

    def test_feeling_safe_headline_is_the_gender_gap(self, data):
        gap = headline_scores(data).query("code == '10_2'").set_index("ref_area")
        assert gap["obs_value"].to_dict() == {"DEU": 5.0, "FRA": 20.0, "ITA": 2.0}
        assert gap["name"].iloc[0] == "Gender gap in feeling safe at night"
        assert gap["score"].to_dict() == pytest.approx({"DEU": 15 / 18, "FRA": 0.0, "ITA": 1.0})

    def test_non_headline_measures_are_left_out(self, data):
        assert "11_1" not in set(headline_scores(data)["code"])

    def test_future_uses_the_capital_headlines(self, data):
        assert set(headline_scores(data, "future")["code"]) == {"12_8"}


class TestWellbeingIndex:
    # Dimension scores (income | health | safety) and the equal-weight overall score:
    #   FRA  (0.5+1)/2 = 0.75 | 1 | 0       -> 1.75/3     = 0.583
    #   DEU  (1+0.5)/2 = 0.75 | 0 | 15/18   -> 1.583/3    = 0.528
    #   ITA  (0+0)/2   = 0    | - | 1       -> 1/2        = 0.5 (no health data)

    def test_equal_weights_follow_how_s_life(self, data):
        scores = wellbeing_index(data).scores.set_index("ref_area")
        assert scores["score"].to_dict() == pytest.approx(
            {"FRA": 1.75 / 3, "DEU": (0.75 + 15 / 18) / 3, "ITA": 0.5}
        )
        assert scores["rank"].to_dict() == {"FRA": 1, "DEU": 2, "ITA": 3}
        assert scores.loc["ITA", "dimensions"] == 2

    def test_each_dimension_counts_once_however_many_indicators(self, data):
        dimensions = wellbeing_index(data).dimension_scores.set_index(["ref_area", "dimension"])
        assert dimensions.loc[("FRA", "Income and wealth"), "score"] == pytest.approx(0.75)
        assert dimensions.loc[("FRA", "Income and wealth"), "indicators"] == 2

    def test_named_better_life_36_with_separate_current_and_future_scores(self, data):
        assert wellbeing_index(data).name == "Better Life 36: current well-being"
        future = wellbeing_index(data, kind="future")
        assert future.name == "Better Life 36: future well-being"
        assert future.scores["ref_area"].tolist() == ["FRA", "ITA", "DEU"]  # emissions only

    def test_zero_weight_drops_a_dimension(self, data):
        # Without health: FRA 0.75/2, DEU (0.75+0.833)/2, ITA 0.5
        ranks = wellbeing_index(data, {"Health": 0}).scores.set_index("ref_area")["rank"]
        assert ranks.to_dict() == {"DEU": 1, "ITA": 2, "FRA": 3}

    def test_dimensions_by_number_or_name(self, data):
        # Safety x3: FRA 1.75/5, DEU (0.75+2.5)/5, ITA 3/4
        by_number = wellbeing_index(data, {10: 3}).scores
        by_name = wellbeing_index(data, {"safety": 3}).scores
        by_text = wellbeing_index(data, {"10": 3}).scores  # JSON keys arrive as strings
        assert by_number["ref_area"].tolist() == ["ITA", "DEU", "FRA"]
        assert by_name["score"].tolist() == pytest.approx(by_number["score"].tolist())
        assert by_text["score"].tolist() == pytest.approx(by_number["score"].tolist())

    @pytest.mark.parametrize(
        ("weights", "message"),
        [
            ({"Happiness": 2}, "Unknown current well-being dimension"),
            ({12: 1}, "Unknown current well-being dimension"),  # a capital, not a dimension
            ({"Health": -1}, "at least 0"),
            ({n: 0 for n in range(1, 12)}, "At least one dimension"),
        ],
    )
    def test_invalid_weights(self, data, weights, message):
        with pytest.raises(AnalysisError, match=message):
            wellbeing_index(data, weights)


class TestCountryProfile:
    def test_ranks_tiers_and_oecd_average(self, data):
        profile = country_profile(data, "fra")
        rows = profile.indicators.set_index("code")
        assert rows.loc["1_1", ["rank", "out_of", "tier"]].tolist() == [2, 3, "middle third"]
        assert rows.loc["1_1", "oecd_average"] == pytest.approx(40.0)  # BRA not averaged
        assert not rows.loc["1_1", "better_than_oecd"]  # equal to the average isn't better
        assert rows.loc["1_2", "better_than_oecd"]  # lower inequality than average
        assert profile.strengths == ["S80/S20", "Emissions"]
        assert profile.weaknesses == ["Gender gap in feeling safe at night"]
        assert profile.overall["current"] == {"score": pytest.approx(1.75 / 3), "rank": 1,
                                              "out_of": 3}  # fmt: skip

    def test_partner_countries_are_refused(self, data):
        with pytest.raises(AnalysisError, match="not OECD member"):
            country_profile(data, "BRA")

    def test_missing_headline_indicators_are_listed(self, data):
        caveats = " ".join(country_profile(data, "ITA").caveats)
        assert "Life expectancy" in caveats


@pytest.mark.parametrize(
    ("rank", "out_of", "tier"),
    [(1, 38, "top third"), (12, 38, "top third"), (13, 38, "middle third"),
     (25, 38, "middle third"), (26, 38, "bottom third"), (None, 38, None)],
)  # fmt: skip
def test_tiers_are_thirds_of_members_with_data(rank, out_of, tier):
    assert _tier(rank, out_of) == tier
