"""Does our method reproduce the OECD's own published numbers? Checked against the live data.

Skipped by default: run with `uv run pytest -m live`.

The figures are OECD averages quoted in How's Life? 2024, Chapter 1. Only indicators where the
database hasn't visibly been revised since publication are used: for others (household income,
homicides, deaths of despair, overcrowding, the gender wage gap) today's data differ from the
report by 5-20%, most likely because of revisions since November 2024.
"""

import pytest

from wise_mcp.analysis import latest, oecd_average, wellbeing_index

pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    ("code", "year", "published"),
    [
        ("5_1", 2022, 80.7),  # "A newborn in 2022 could expect to live 80.7 years"
        ("2_1", 2023, 78.0),  # "In 2023, 78% of those aged 25-64 were employed"
        ("3_2", 2022, 79.0),  # "79% of their disposable income left after housing costs"
        ("2_7", 2022, 100 / 14),  # "Around one in 14 employees ... worked long hours"
    ],
)
def test_oecd_averages_match_how_s_life_2024(live_data, code, year, published):
    average = oecd_average(latest(live_data, code, year=year))
    assert average.value == pytest.approx(published, rel=0.025)


def test_overall_ranking_matches_the_report_s_picture(live_data):
    # How's Life? 2024, Chapter 4: most Nordic countries and the Netherlands are among the highest
    # performers, and several Latin American countries among the lowest.
    ranking = wellbeing_index(live_data).scores["ref_area"].tolist()
    nordics = {"DNK", "FIN", "ISL", "NOR", "SWE"}
    assert len(nordics & set(ranking[:10])) >= 3
    assert len({"MEX", "COL", "CHL", "CRI"} & set(ranking[-8:])) >= 2
