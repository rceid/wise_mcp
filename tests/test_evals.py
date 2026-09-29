"""The eval report: every case runs, and the naive helpers really make the mistakes they claim."""

import pytest
from builders import make_data, series

from evals import cases
from evals.run import raw_data, report
from wise_mcp.catalog import Measure


def test_the_report_runs_on_any_data(store):
    # The fixture lacks most measures: those cases say "no answer" instead of failing the run.
    text = report(store)
    assert text.count("\n### ") == len(cases.CASES)
    assert "Against the OECD's published figures" in text


def test_case_ids_are_unique():
    ids = [case.id for case in cases.CASES]
    assert len(ids) == len(set(ids))


def test_every_case_explains_the_difference():
    assert all(case.pitfall and case.question.endswith("?") for case in cases.CASES)


def test_the_naive_mean_mixes_in_partners_and_breakdowns(store):
    raw = raw_data(store)
    naive = cases._naive_mean("11_1", 2021)(raw, None)
    areas = int(naive.split(", ")[-1].split()[0])
    assert areas > len(raw[(raw["measure"] == "11_1") & raw["ref_area"].isin(["FRA", "DEU", "MEX"])]
                       ["ref_area"].unique()) - 1  # fmt: skip


def test_naive_ranking_ignores_direction():
    # Homicides: lower is better, but the naive sort puts the highest rate first.
    rows = series("10_1", {"FRA": {2024: 1.0}, "MEX": {2024: 25.0}, "DEU": {2024: 0.8}})
    data = make_data(rows, {"10_1": Measure("10_1", "lower")})
    naive = cases._naive_top("10_1")(data.observations, data)
    assert naive.startswith("MEX") and cases.top(data, "10_1").startswith("DEU")


@pytest.mark.parametrize("case", [c for c in cases.CASES if c.published_value])
def test_published_cases_carry_their_number(case):
    assert case.published and case.published_value > 0
