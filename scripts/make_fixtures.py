"""Rebuild the test fixtures from the live OECD API (2 requests).

Tests parse small slices of real API responses, so they exercise the actual CSV format
without calling the API. Re-run this if the OECD changes its format and the live tests fail:

    uv run python scripts/make_fixtures.py
"""

import csv
import io
from pathlib import Path

from wise_mcp.config import AGENCY_ID, DATAFLOWS
from wise_mcp.sdmx import SdmxClient

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

# France, Mexico and Germany cover several observation statuses (normal, break, estimate)
# and different latest years.
COUNTRIES = {"FRA", "MEX", "DEU"}
MEASURES = {
    "current": {"11_1", "10_2"},  # life satisfaction; feeling safe at night (split by sex, age)
    "future": {"12_14", "15_1"},  # material footprint per capita; produced fixed assets
}
FIRST_YEAR = 2018


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with SdmxClient() as client:
        for name, dataflow_id in DATAFLOWS.items():
            text = client.fetch_dataflow_csv(AGENCY_ID, dataflow_id)
            rows = csv.reader(io.StringIO(text))
            header = next(rows)
            area, measure, year = (header.index(c) for c in ("REF_AREA", "MEASURE", "TIME_PERIOD"))
            kept = [
                row
                for row in rows
                if row[area] in COUNTRIES
                and row[measure] in MEASURES[name]
                and int(row[year]) >= FIRST_YEAR
            ]
            kept.sort(key=lambda row: (row[area], row[measure], row[year]))
            out = FIXTURES / f"{name}_sample.csv"
            with out.open("w", newline="") as f:
                writer = csv.writer(f, lineterminator="\n")
                writer.writerow(header)
                writer.writerows(kept)
            print(f"{out.name}: {len(kept)} rows from {len(text):,} characters")


if __name__ == "__main__":
    main()
