import pytest
from builders import make_data, series

from wise_mcp.analysis import AnalysisError, assess, trend
from wise_mcp.analysis.trends import Period
from wise_mcp.catalog import Measure

LIFE_SATISFACTION = Measure("11_1", "higher", threshold=0.2)


@pytest.mark.parametrize(
    ("measure", "start", "end", "expected"),
    [
        (LIFE_SATISFACTION, 7.0, 7.3, "improving"),
        (LIFE_SATISFACTION, 7.0, 7.1, "no clear change"),
        (LIFE_SATISFACTION, 7.3, 7.0, "deteriorating"),
        # 7.2 - 6.9 is 0.29999999999999982 in floating point: exactly the threshold still counts.
        (Measure("x", "higher", threshold=0.3), 6.9, 7.2, "improving"),
        (Measure("x", "lower", threshold=0.3), 3.5, 3.0, "improving"),  # homicides falling
        # Target: the gap narrowed from 5 to 3 points even though it changed sign.
        (Measure("x", "target", target=0, threshold=1), 5.0, -3.0, "improving"),
        (Measure("x", "target", target=0, threshold=1), 2.0, -2.5, "no clear change"),
        (Measure("x", "higher", threshold=0), 0.5, 0.5001, "improving"),  # any change counts
        (Measure("x", "higher", threshold=0), 0.5, 0.5, "no clear change"),
        (Measure("x", "higher"), 400, 380, "no threshold"),  # PISA: confidence intervals
    ],
)
def test_assess(measure, start, end, expected):
    assert assess(measure, start, end) == expected


def changes_for(values, since=2010, measure=LIFE_SATISFACTION, **kwargs):
    data = make_data(series(measure.code, values), {measure.code: measure})
    return trend(data, measure.code, since=since, **kwargs).changes.set_index("ref_area")


class TestPeriods:
    def test_around_2010_is_the_earliest_year_in_2010_to_2015(self):
        row = changes_for({"FRA": {2008: 6.0, 2012: 7.0, 2014: 7.1, 2024: 7.4}}).loc["FRA"]
        assert (row["start_year"], row["end_year"], row["assessment"]) == (2012, 2024, "improving")

    def test_2019_is_the_latest_pre_pandemic_year(self):
        row = changes_for({"FRA": {2017: 7.0, 2018: 7.4, 2022: 7.1}}, since="2019").loc["FRA"]
        assert (row["start_year"], row["assessment"]) == (2018, "deteriorating")

    def test_the_end_must_be_after_2019(self):
        row = changes_for({"FRA": {2010: 7.0, 2019: 7.5}}).loc["FRA"]
        assert row["assessment"] == "insufficient data"

    def test_no_baseline_in_the_window(self):
        assert changes_for({"FRA": {2016: 7.0, 2024: 7.5}}).loc["FRA", "assessment"] == (
            "insufficient data"
        )

    def test_custom_start_year(self):
        row = changes_for({"FRA": {2014: 5.0, 2016: 7.0, 2024: 7.0}}, since=2015).loc["FRA"]
        assert (row["start_year"], row["assessment"]) == (2016, "no clear change")

    def test_invalid_start(self):
        with pytest.raises(AnalysisError, match="must be a year"):
            Period.since("last decade")


def test_series_break_during_the_period_is_flagged():
    rows = series("11_1", {"FRA": {2010: 7.0, 2024: 7.4}, "DEU": {2010: 7.0, 2024: 7.4}})
    rows[0]["obs_status"] = "B"  # a break in the baseline year itself doesn't affect the change
    rows[3]["obs_status"] = "B"  # DEU 2024: the method changed during the period
    data = make_data(rows, {"11_1": LIFE_SATISFACTION})
    result = trend(data, "11_1")
    assert result.changes.set_index("ref_area")["series_break"].to_dict() == {
        "DEU": True, "FRA": False,
    }  # fmt: skip
    assert any("Series breaks in DEU" in c for c in result.caveats)


class TestOecdChange:
    VALUES = {
        "FRA": {2010: 7.0, 2024: 7.4},
        "DEU": {2010: 7.0, 2024: 7.0},
        "ITA": {2024: 6.0},  # no baseline: must not drag the end average down
        "BRA": {2010: 5.0, 2024: 9.0},  # partner: excluded
    }

    def test_average_over_members_with_both_years(self):
        data = make_data(series("11_1", self.VALUES), {"11_1": LIFE_SATISFACTION})
        oecd = trend(data, "11_1").oecd
        assert oecd["countries"] == 2
        assert oecd["start_value"] == pytest.approx(7.0)
        assert oecd["end_value"] == pytest.approx(7.2)
        assert oecd["assessment"] == "improving"

    def test_asking_about_one_country_keeps_the_full_average(self):
        data = make_data(series("11_1", self.VALUES), {"11_1": LIFE_SATISFACTION})
        result = trend(data, "11_1", countries=["FRA"])
        assert result.changes["ref_area"].tolist() == ["FRA"]
        assert result.oecd["countries"] == 2


def test_series_for_charts_starts_at_the_period_even_without_an_assessment():
    values = {"FRA": {2008: 6.0, 2010: 7.0, 2015: 7.2, 2024: 7.4}, "DEU": {2011: 7.0, 2012: 7.1}}
    data = make_data(series("11_1", values), {"11_1": LIFE_SATISFACTION})
    result = trend(data, "11_1")
    shown = result.series.groupby("ref_area")["time_period"].apply(list).to_dict()
    # DEU has no value after 2019, so its change can't be assessed, but its line still shows.
    assert shown == {"DEU": [2011, 2012], "FRA": [2010, 2015, 2024]}
    assert result.changes.set_index("ref_area").loc["DEU", "assessment"] == "insufficient data"


def test_no_threshold_is_explained():
    pisa = Measure("6_2", "higher", note="Uses PISA confidence intervals.")
    data = make_data(series("6_2", {"FRA": {2012: 495.0, 2022: 474.0}}), {"6_2": pisa})
    result = trend(data, "6_2")
    assert result.changes.loc[0, "assessment"] == "no threshold"
    assert "no fixed threshold" in result.caveats[0] and "PISA" in result.caveats[0]


class TestPooledMeasures:
    TRUST = Measure("14_3", "higher", threshold=3, pooled=True)
    VALUES = {
        c: {2008: 44 + i, 2009: 44 + i, 2010: 44 + i, 2011: 40 + i, 2012: 40 + i, 2013: 40 + i,
            2023: 37 + i, 2024: 37 + i, 2025: 37 + i}
        for i, c in enumerate(["FRA", "DEU", "ITA", "ESP", "NLD"])
    }  # fmt: skip

    def result(self):
        data = make_data(series("14_3", self.VALUES), {"14_3": self.TRUST})
        return trend(data, "14_3", ["FRA"])

    def test_charts_get_one_row_per_whole_period(self):
        result = self.result()
        assert result.series["period"].tolist() == ["2008–10", "2011–13", "2023–25"]
        assert result.oecd_line["period"].tolist() == ["2008–10", "2011–13", "2023–25"]

    def test_the_assessment_is_unchanged_and_the_periods_are_explained(self):
        result = self.result()
        row = result.changes.set_index("ref_area").loc["FRA"]
        assert (row["start_year"], row["end_year"], row["assessment"]) == (
            2010, 2025, "deteriorating",
        )  # fmt: skip
        assert any(
            "2010 stands for 2008–10 and 2025 stands for 2023–25" in c for c in result.caveats
        )
