"""Checks against the real OECD API, to catch changes on their side.

Skipped by default. Run with `uv run pytest -m live`; costs 2 of the ~60 requests/hour.
"""

import pandas as pd
import pytest

from wise_mcp.catalog import load_measures
from wise_mcp.config import AGENCY_ID, DATAFLOWS
from wise_mcp.sdmx import SdmxClient, parse_labelled_csv

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def raw_csv() -> dict[str, str]:
    with SdmxClient() as client:
        return {
            name: client.fetch_dataflow_csv(AGENCY_ID, flow) for name, flow in DATAFLOWS.items()
        }


def test_current_wellbeing_has_all_11_dimensions(raw_csv):
    download = parse_labelled_csv(raw_csv["current"])
    obs = download.observations

    assert download.structure_id.startswith("OECD.WISE.WDP:DSD_HSL@DF_HSL_CWB(")
    assert set(obs["domain"]) == {f"HSL_{i}" for i in range(1, 12)}
    assert obs["ref_area"].nunique() >= 38  # every OECD member, plus partner countries
    assert (obs["unit_mult"] == 0).all()  # if this changes, values need scaling by 10^unit_mult


def test_future_wellbeing_has_all_4_capitals(raw_csv):
    download = parse_labelled_csv(raw_csv["future"])

    assert download.structure_id.startswith("OECD.WISE.WDP:DSD_HSL@DF_HSL_FWB(")
    assert set(download.observations["domain"]) == {f"HSL_{i}" for i in range(12, 16)}


@pytest.mark.parametrize("name", DATAFLOWS)
def test_saved_fixtures_match_live_csv_header(raw_csv, name, request):
    # If this fails, the fixtures no longer look like real responses: rerun
    # scripts/make_fixtures.py and check what changed.
    fixture = request.getfixturevalue(f"{name}_csv")
    assert raw_csv[name].splitlines()[0] == fixture.splitlines()[0]


@pytest.fixture(scope="module")
def observations(raw_csv) -> pd.DataFrame:
    return pd.concat(parse_labelled_csv(text).observations for text in raw_csv.values())


def test_measures_yaml_covers_exactly_the_live_measures(observations):
    # A failure means the OECD added or removed a measure: update measures.yaml to match.
    assert set(load_measures()) == set(observations["measure"])


def test_measures_published_in_several_units_have_a_default(observations):
    # Totals never use the "_SUB" units, which are for breakdowns by sex, age or education.
    totals = observations[~observations["unit_measure"].str.endswith("_SUB")]
    units = totals.groupby("measure")["unit_measure"].unique()
    measures = load_measures()
    for code, published in units.items():
        if len(published) > 1:
            assert measures[code].unit in published, f"{code} needs a unit: one of {published}"
