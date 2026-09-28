"""Chart templates, checked on their Vega-Lite specs rather than pixels: each test asserts one
thing the chart promises, such as the OECD line sitting at the OECD average."""

import pytest
from builders import make_data, obs, series

from wise_mcp import analysis
from wise_mcp.analysis import AnalysisError, WellbeingData
from wise_mcp.catalog import Measure
from wise_mcp.charts import export, templates
from wise_mcp.charts.style import SOURCE

LIFE_SATISFACTION = Measure("11_1", "higher", threshold=0.2, name="Life satisfaction")


@pytest.fixture
def data(store) -> WellbeingData:
    # Real OECD response slices: France, Mexico, Germany; 2018 onwards (see tests/fixtures).
    return WellbeingData.from_store(store)


def units(spec: dict) -> list[dict]:
    """Every single-mark chart inside a layered or stacked spec."""
    found = []

    def walk(node: dict) -> None:
        if "mark" in node:
            found.append(node)
        for key in ("layer", "vconcat", "hconcat", "concat"):
            for child in node.get(key, []):
                walk(child)

    walk(spec)
    return found


def mark(unit: dict) -> str:
    return unit["mark"] if isinstance(unit["mark"], str) else unit["mark"]["type"]


def values(spec: dict, unit: dict) -> list[dict]:
    data = unit.get("data") or spec.get("data")
    return spec["datasets"][data["name"]] if "name" in data else data["values"]


def y_order(unit: dict) -> list[str]:
    return unit["encoding"]["y"]["sort"]


def subtitle(spec: dict) -> list[str]:
    return spec["title"]["subtitle"]


class TestRankings:
    def test_oecd_average_line_and_best_first_order_with_years(self, data):
        comparison = analysis.compare_countries(data, "11_1")
        spec = export.spec(templates.ranked_bars(comparison))
        bars, rule = units(spec)[0], next(u for u in units(spec) if mark(u) == "rule")
        assert values(spec, rule)[0]["x"] == pytest.approx(comparison.oecd_average.value)
        assert values(spec, rule)[0]["label"].startswith("OECD 3 average")
        assert y_order(bars)[0].startswith("Mexico · 2021")  # the highest life satisfaction
        assert bars["encoding"]["x"]["scale"]["zero"] is True  # bars always start at zero

    def test_dot_plot_zooms_to_the_data(self, data):
        spec = export.spec(templates.dot_plot(analysis.compare_countries(data, "11_1")))
        assert units(spec)[0]["encoding"]["x"]["scale"]["zero"] is False

    def test_highlighted_countries(self, data):
        spec = export.spec(templates.dot_plot(analysis.compare_countries(data, "11_1"), ["FRA"]))
        rows = values(spec, units(spec)[0])
        assert {r["ref_area"] for r in rows if r["highlight"]} == {"FRA"}

    def test_flagged_values_are_marked_in_labels_and_explained(self, data):
        spec = export.spec(templates.ranked_bars(analysis.compare_countries(data, "11_1")))
        assert any(label.endswith("†") for label in y_order(units(spec)[0]))
        assert any(line.startswith("† flagged value") for line in subtitle(spec))

    def test_lower_is_better_puts_the_lowest_first(self):
        rows = series("10_1", {"FRA": {2024: 1.0}, "DEU": {2024: 0.8}, "ITA": {2024: 0.5}})
        data = make_data(rows, {"10_1": Measure("10_1", "lower")})
        spec = export.spec(templates.ranked_bars(analysis.compare_countries(data, "10_1")))
        assert y_order(units(spec)[0])[0].startswith("Country ITA")
        assert "lower is better" in subtitle(spec)[0]

    def test_a_non_zero_target_gets_its_own_line(self):
        rows = series("14_5", {"FRA": {2024: 37.0}, "MEX": {2024: 50.4}})
        data = make_data(rows, {"14_5": Measure("14_5", "target", target=50)})
        spec = export.spec(templates.ranked_bars(analysis.compare_countries(data, "14_5")))
        rules = [values(spec, u)[0]["x"] for u in units(spec) if mark(u) == "rule"]
        assert 50 in rules


class TestTrends:
    FIVE = {c: {2010: 7.0 + i / 10, 2011: 7.1 + i / 10, 2012: 7.2} for i, c in
            enumerate(["FRA", "DEU", "ITA", "ESP", "NLD"])}  # fmt: skip

    def test_lines_with_an_oecd_average_over_members_with_every_year(self):
        data = make_data(series("11_1", self.FIVE), {"11_1": LIFE_SATISFACTION})
        spec = export.spec(templates.trend_lines(analysis.trend(data, "11_1", ["FRA", "DEU"])))
        oecd = next(u for u in units(spec) if u["mark"].get("strokeDash"))
        assert [row["time_period"] for row in values(spec, oecd)] == [2010, 2011, 2012]
        assert "5 members with data in every year to 2012" in " ".join(subtitle(spec))

    def test_at_most_four_lines(self):
        data = make_data(series("11_1", self.FIVE), {"11_1": LIFE_SATISFACTION})
        with pytest.raises(AnalysisError, match="up to 4 countries"):
            templates.trend_lines(analysis.trend(data, "11_1", list(self.FIVE)))

    def test_series_breaks_are_marked(self):
        rows = series("11_1", {"FRA": {2010: 7.0, 2024: 7.4}})
        rows[1]["obs_status"] = "B"
        spec = export.spec(
            templates.trend_lines(
                analysis.trend(make_data(rows, {"11_1": LIFE_SATISFACTION}), "11_1", ["FRA"])
            )
        )
        diamonds = [u for u in units(spec) if u["mark"].get("shape") == "diamond"]
        assert diamonds and any("series break" in line for line in subtitle(spec))

    def test_change_arrows_order_oecd_first_then_most_improved(self):
        # Homicides, lower is better: ITA fell most, so it comes right after the OECD row.
        rows = series(
            "10_1", {"FRA": {2010: 1.0, 2022: 0.9}, "ITA": {2010: 1.0, 2022: 0.2}, "DEU": {2010:
            1.0, 2022: 1.5}, "MEX": {2024: 20.0}},
        )  # fmt: skip
        data = make_data(rows, {"10_1": Measure("10_1", "lower", threshold=0.3)})
        spec = export.spec(templates.change_arrows(analysis.trend(data, "10_1")))
        order = y_order(units(spec)[0])
        assert order[0].startswith("OECD average")
        assert [label.split(" · ")[0] for label in order[1:]] == [
            "Country ITA", "Country FRA", "Country DEU",
        ]  # fmt: skip
        assert "Not enough data: MEX" in subtitle(spec)

    def test_judgements_carry_a_glyph_not_just_colour(self, data):
        spec = export.spec(templates.change_arrows(analysis.trend(data, "11_1", since="2019")))
        dot = next(u for u in units(spec) if "fill" in u["encoding"])
        domain = dot["encoding"]["fill"]["scale"]["domain"]
        assert domain and all(label[0] in "▲▼●○–" for label in domain)


class TestGapsAndCountries:
    def test_gap_dots_put_the_oecd_first_then_the_widest_gap(self, data):
        spec = export.spec(templates.gap_dots(analysis.group_gaps(data, "10_2", "sex")))
        order = y_order(units(spec)[1])
        assert order[0].startswith("OECD average (3 members)")
        gaps = analysis.group_gaps(data, "10_2", "sex").summary.set_index("ref_area_label")
        widest = (gaps["F_vs_M"] - 1).abs().idxmax()
        assert order[1].startswith(widest)

    def test_profile_has_current_and_future_panels(self, data):
        spec = export.spec(templates.profile_scores(analysis.country_profile(data, "FRA")))
        assert [panel["title"] for panel in spec["vconcat"]] == [
            "Current well-being", "Future well-being",
        ]  # fmt: skip

    def test_trend_grid_compares_the_country_with_the_oecd(self, data):
        result = analysis.country_trends(data, "FRA", since="2019")
        spec = export.spec(templates.trend_grid(result))
        boxes = units(spec)[0]
        assert boxes["encoding"]["x"]["sort"] == ["France", "OECD average"]
        assert len(values(spec, boxes)) == 2 * len(result.indicators)

    def test_index_ranking_highlights(self, data):
        spec = export.spec(templates.index_ranking(analysis.wellbeing_index(data), ["MEX"]))
        rows = values(spec, units(spec)[0])
        assert {r["ref_area"] for r in rows if r["highlight"]} == {"MEX"}


def test_every_chart_cites_its_source_and_uses_the_house_style(data):
    spec = export.spec(templates.dot_plot(analysis.compare_countries(data, "11_1")))
    assert subtitle(spec)[-1] == SOURCE
    assert spec["config"]["background"] == "#fcfcfb"


def test_png_rendering(data):
    chart = templates.dot_plot(analysis.compare_countries(data, "11_1"))
    full, thumbnail = export.png(chart), export.png(chart, export.THUMBNAIL_SCALE)
    assert full[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(thumbnail) < len(full)


def test_no_data_for_the_period_is_a_clear_error():
    rows = [obs("FRA", "11_1", 2024, 7.0), obs("DEU", "11_1", 2024, 7.2)]  # no 2010 baseline
    data = make_data(rows, {"11_1": LIFE_SATISFACTION})
    with pytest.raises(AnalysisError, match="No country has data"):
        templates.change_arrows(analysis.trend(data, "11_1"))
