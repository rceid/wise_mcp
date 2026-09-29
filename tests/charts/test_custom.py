"""Custom charts: Claude's Vega-Lite spec, drawn over rows the server supplies."""

import pytest
from builders import make_data, series

from wise_mcp.analysis import AnalysisError, WellbeingData
from wise_mcp.catalog import Measure
from wise_mcp.charts import custom, export

BARS = {
    "mark": "bar",
    "encoding": {
        "y": {"field": "country", "type": "nominal"},
        "x": {"field": "value", "type": "quantitative"},
    },
}


@pytest.fixture
def data(store) -> WellbeingData:
    return WellbeingData.from_store(store)


def test_the_server_supplies_the_rows_and_labels_the_chart(data):
    drawing = custom.custom_chart(data, "11_1", {**BARS, "title": "My chart"})
    spec = drawing.chart
    assert {row["code"] for row in spec["data"]["values"]} == {"FRA", "DEU", "MEX"}
    assert spec["title"]["text"] == "My chart"
    assert custom.NOTE in spec["title"]["subtitle"]
    assert "| France (FRA) |" in drawing.table
    assert export.png_from_spec(spec)[:4] == b"\x89PNG"


def test_series_rows_include_the_oecd_average():
    # An OECD trend line needs five members with every year.
    values = {c: {2019: 7.0, 2024: 7.2} for c in ["FRA", "DEU", "ITA", "ESP", "NLD"]}
    data = make_data(series("11_1", values), {"11_1": Measure("11_1", "higher", threshold=0.2)})
    drawing = custom.custom_chart(data, "11_1", BARS, rows="series", countries=["FRA"],
                                  since="2019")  # fmt: skip
    codes = {row["code"] for row in drawing.chart["data"]["values"]}
    assert codes == {"FRA", "OECD"}


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({**BARS, "data": {"url": "https://example.com/x.csv"}}, "Leave out data, url"),
        ({"layer": [{**BARS, "transform": [{"lookup": "code", "from": {"data": {"url": "x"}}}]}]},
         "Leave out data, url"),
        ({"mark": "barr"}, "'barr' isn't allowed there"),
        ({**BARS, "description": "x" * 30_000}, "over 20 KB"),
    ],
)  # fmt: skip
def test_specs_that_fetch_data_or_are_invalid_are_refused(data, spec, message):
    with pytest.raises(AnalysisError, match=message):
        custom.custom_chart(data, "11_1", spec)
