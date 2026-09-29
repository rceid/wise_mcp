"""Which charts get suggested for which question, and drawing a chart from its id."""

import pytest
from builders import make_data, series

from wise_mcp.analysis import AnalysisError, WellbeingData
from wise_mcp.catalog import Measure
from wise_mcp.charts import catalog


@pytest.fixture
def data(store) -> WellbeingData:
    # Real OECD response slices: France, Mexico, Germany; 2018 onwards (see tests/fixtures).
    return WellbeingData.from_store(store)


def names(options) -> list[str]:
    return [option.id.split("?")[0] for option in options]


class TestChartIds:
    def test_an_id_spells_out_the_chart(self):
        chart_id = catalog.chart_id("dot_plot", measure="11_1", highlight=["FRA", "DEU"])
        assert chart_id == "dot_plot?measure=11_1&highlight=FRA,DEU"
        assert catalog.chart_id("index_ranking", highlight=None) == "index_ranking"

    def test_drawing_from_an_id_returns_the_chart_and_its_table(self, data):
        drawing = catalog.draw(data, "dot_plot?measure=11_1&highlight=FRA")
        assert drawing.chart.to_dict()["title"]["text"] == "Life satisfaction"
        assert "| France (FRA) |" in drawing.table  # the table view of the same data

    @pytest.mark.parametrize(
        ("chart_id", "message"),
        [
            ("pie_chart?measure=11_1", "Unknown chart"),
            ("dot_plot?measure=11_1&colour=red", "doesn't fit dot_plot"),
            ("dot_plot?measure=99_9", "Unknown measure"),
        ],
    )
    def test_bad_ids_explain_themselves(self, data, chart_id, message):
        with pytest.raises(AnalysisError, match=message):
            catalog.draw(data, chart_id)


class TestSuggestions:
    def test_values_far_from_zero_get_dots_first(self, data):
        # Life satisfaction runs from about 6 to 8.5: bars from zero would squash it.
        options = catalog.suggest(data, measure="11_1")
        assert names(options)[0] == "dot_plot"
        assert "bunched far from zero" in options[0].why

    def test_values_near_zero_get_bars_first_and_dots_as_the_alternative(self):
        rows = series("10_1", {"FRA": {2024: 0.8}, "USA": {2024: 6.0}, "MEX": {2024: 25.0}})
        data = make_data(rows, {"10_1": Measure("10_1", "lower")})
        options = catalog.suggest(data, measure="10_1")
        assert names(options) == ["ranked_bars", "change_arrows", "tile_map", "dot_plot"]
        assert options[-1].why.startswith("Alternative view")

    def test_a_few_countries_get_a_line_chart(self, data):
        options = catalog.suggest(data, measure="11_1", countries=["France", "DEU"])
        assert "trend_lines" in names(options)
        assert "highlight=FRA,DEU" in options[0].id

    def test_more_countries_than_lines_get_no_line_chart(self):
        rows = series("11_1", {c: {2024: 7.0} for c in ["FRA", "DEU", "ITA", "ESP", "NLD"]})
        data = make_data(rows, {"11_1": Measure("11_1", "higher")})
        options = catalog.suggest(
            data, measure="11_1", countries=["FRA", "DEU", "ITA", "ESP", "NLD"]
        )
        assert "trend_lines" not in names(options)

    def test_gap_charts_only_for_measures_with_breakdowns(self, data):
        assert "gap_dots" in names(catalog.suggest(data, measure="10_2"))
        assert "gap_dots" not in names(catalog.suggest(data, measure="12_14"))

    def test_uncomparable_measures_are_never_ranked(self):
        rows = series("12_4", {"CAN": {2016: 2_000_000.0}, "FRA": {2016: 10.0}})
        data = make_data(rows, {"12_4": Measure("12_4", "higher", comparable=False)})
        assert not {"ranked_bars", "dot_plot"} & set(names(catalog.suggest(data, measure="12_4")))

    def test_a_country_question_gets_the_country_views(self, data):
        options = catalog.suggest(data, country="France")
        assert names(options) == ["trend_grid", "profile_scores", "index_ranking"]

    def test_the_question_must_be_about_something(self, data):
        with pytest.raises(AnalysisError, match="a measure, a country, or both"):
            catalog.suggest(data)

    @pytest.mark.parametrize(
        "question",
        [{"measure": "11_1", "countries": ["FRA"]}, {"measure": "10_2"}, {"country": "MEX"}],
    )
    def test_every_suggestion_can_be_drawn(self, data, question):
        for option in catalog.suggest(data, since="2019", **question):
            assert catalog.draw(data, option.id).chart is not None


class TestPanelTabs:
    def test_tabs_are_the_suggestions_for_the_same_question(self, data):
        options = catalog.related(data, "trend_lines?measure=11_1&countries=FRA&since=2019")
        suggested = catalog.suggest(data, measure="11_1", countries=["FRA"], since="2019")
        assert names(options) == names(suggested)

    def test_the_chart_keeps_its_own_id_even_without_the_default_baseline(self):
        # "since=2010" is the default: the chart must not appear twice.
        values = {c: {2010: 6.0 + i, 2024: 7.0 + i} for i, c in enumerate(["FRA", "DEU", "ITA"])}
        data = make_data(series("11_1", values), {"11_1": Measure("11_1", "higher")})
        ids = [o.id for o in catalog.related(data, "change_arrows?measure=11_1")]
        assert "change_arrows?measure=11_1" in ids
        assert "change_arrows?measure=11_1&since=2010" not in ids

    def test_charts_without_the_data_to_draw_are_left_out(self, data):
        # The fixture starts in 2018, so nothing can be assessed since 2010.
        ids = [o.id for o in catalog.related(data, "dot_plot?measure=11_1")]
        assert not any(i.startswith("change_arrows") for i in ids)

    def test_a_country_picture_offers_the_other_country_pictures(self, data):
        options = catalog.related(data, "index_ranking?highlight=FRA")
        assert names(options) == ["trend_grid", "profile_scores", "index_ranking"]

    @pytest.mark.parametrize(
        ("chart_id", "label"),
        [("dot_plot?measure=11_1", "Ranking (dots)"), ("gap_dots?measure=10_2&by=age",
         "Gaps by age"), ("trend_grid?country=FRA", "Trends")],
    )  # fmt: skip
    def test_tab_labels(self, chart_id, label):
        assert catalog.tab_label(chart_id) == label
