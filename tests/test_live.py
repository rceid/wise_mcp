"""Checks against the real OECD API, to catch changes on their side.

Skipped by default. Run with `uv run pytest -m live`; costs 2 of the ~60 requests/hour.
"""

import pytest

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
