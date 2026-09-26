import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wise_mcp.config import DATAFLOWS
from wise_mcp.sdmx import DataflowDownload, parse_labelled_csv
from wise_mcp.store import DataStore

FIXTURES = Path(__file__).parent / "fixtures"


class FakeFetcher:
    """Stands in for SdmxClient: serves the fixture slices, records calls, fails on demand."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.errors: dict[str, Exception] = {}  # dataflow name -> exception to raise
        self.delay = 0.0

    def fetch_dataflow(self, agency_id: str, dataflow_id: str) -> DataflowDownload:
        name = next(name for name, flow in DATAFLOWS.items() if flow == dataflow_id)
        self.calls.append(name)
        time.sleep(self.delay)
        if name in self.errors:
            raise self.errors[name]
        return parse_labelled_csv((FIXTURES / f"{name}_sample.csv").read_text())

    def fail_all(self, error: Exception) -> None:
        self.errors = {name: error for name in DATAFLOWS}


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def current_csv() -> str:
    return (FIXTURES / "current_sample.csv").read_text()


@pytest.fixture
def future_csv() -> str:
    return (FIXTURES / "future_sample.csv").read_text()


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(tmp_path: Path, fetcher: FakeFetcher, clock: FakeClock) -> DataStore:
    return DataStore(directory=tmp_path / "cache", fetcher=fetcher, clock=clock)
