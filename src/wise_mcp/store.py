"""Local cache of the How's Life? database.

The whole database is two downloads (about 40 MB of labelled CSV, roughly 2 MB over the wire
thanks to gzip), so the store fetches everything at once and answers every read locally. A
refresh costs 2 of the ~60 requests/hour the OECD allows and happens at most once per
CACHE_TTL, so MCP tool calls don't touch the API.

Files in the cache directory:
    current.parquet, future.parquet  observations, codes only (see sdmx.parse_labelled_csv)
    labels.json                      column -> code -> English label, e.g. ref_area/FRA/France
    metadata.json                    when the data was fetched, and which structure version
"""

import json
import logging
import os
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from wise_mcp.config import AGENCY_ID, CACHE_TTL, DATAFLOWS, REFRESH_RETRY_DELAY, cache_dir
from wise_mcp.sdmx import DataflowDownload, SdmxClient, SdmxError

log = logging.getLogger(__name__)


class Fetcher(Protocol):
    """Anything that can download a dataflow: the real SdmxClient, or a fake in tests."""

    def fetch_dataflow(self, agency_id: str, dataflow_id: str) -> DataflowDownload: ...


@dataclass(frozen=True)
class CacheStatus:
    directory: Path
    fetched_at: datetime | None  # None when nothing has been downloaded yet
    is_stale: bool
    dataflows: dict[str, dict[str, Any]]  # name -> {"structure_id", "name", "rows"}


class DataStore:
    def __init__(
        self,
        directory: Path | None = None,
        fetcher: Fetcher | None = None,
        ttl: timedelta = CACHE_TTL,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.directory = directory or cache_dir()
        self._fetcher = fetcher  # None means use a real SdmxClient for each refresh
        self._ttl = ttl
        self._clock = clock
        self._frames: dict[str, pd.DataFrame] = {}
        self._labels: dict[str, dict[str, str]] | None = None
        self._last_failed_refresh: datetime | None = None
        # MCP clients can call several tools in parallel. The lock stops two of them from
        # refreshing at once, which would double the API calls and race on the same files.
        self._lock = threading.RLock()

    def observations(self, dataflow: str) -> pd.DataFrame:
        """All observations for "current" or "future" well-being, refreshing first if due."""
        if dataflow not in DATAFLOWS:
            raise KeyError(f"Unknown dataflow {dataflow!r}, expected one of {list(DATAFLOWS)}")
        with self._lock:
            self._ensure_fresh()
            if dataflow not in self._frames:
                self._frames[dataflow] = pd.read_parquet(self._path(f"{dataflow}.parquet"))
            return self._frames[dataflow]

    def labels(self) -> dict[str, dict[str, str]]:
        """Column -> code -> English label, e.g. ["measure"]["11_1"] is "Life satisfaction"."""
        with self._lock:
            self._ensure_fresh()
            if self._labels is None:
                self._labels = json.loads(self._path("labels.json").read_text())
            return self._labels

    def status(self) -> CacheStatus:
        metadata_file = self._path("metadata.json")
        if not metadata_file.exists():
            return CacheStatus(self.directory, fetched_at=None, is_stale=True, dataflows={})
        metadata = json.loads(metadata_file.read_text())
        fetched_at = datetime.fromisoformat(metadata["fetched_at"])
        return CacheStatus(
            directory=self.directory,
            fetched_at=fetched_at,
            is_stale=self._clock() - fetched_at > self._ttl,
            dataflows=metadata["dataflows"],
        )

    def refresh(self) -> CacheStatus:
        """Download every dataflow and replace the cache. Costs one API request per dataflow."""
        with self._lock:
            with self._open_fetcher() as fetcher:
                downloads = {
                    name: fetcher.fetch_dataflow(AGENCY_ID, dataflow_id)
                    for name, dataflow_id in DATAFLOWS.items()
                }

            # Only now, with every download in memory, is the old copy overwritten. A failure
            # halfway through (rate limit, lost wifi) leaves the previous cache untouched.
            self.directory.mkdir(parents=True, exist_ok=True)
            labels: dict[str, dict[str, str]] = {}
            for name, download in downloads.items():
                self._write_parquet(f"{name}.parquet", download.observations)
                for column, mapping in download.labels.items():
                    labels.setdefault(column, {}).update(mapping)
            self._write_json("labels.json", labels)
            # metadata.json goes last: if a first download is interrupted before this point, there
            # is no metadata, so the cache counts as empty and is fetched again next time.
            self._write_json(
                "metadata.json",
                {
                    "fetched_at": self._clock().isoformat(),
                    "dataflows": {
                        name: {
                            "structure_id": download.structure_id,
                            "name": download.name,
                            "rows": len(download.observations),
                        }
                        for name, download in downloads.items()
                    },
                },
            )

            self._frames.clear()
            self._labels = None
            self._last_failed_refresh = None
            log.info("Refreshed How's Life? cache in %s", self.directory)
            return self.status()

    def _ensure_fresh(self) -> None:
        status = self.status()
        if status.fetched_at is not None and not status.is_stale:
            return

        if (
            self._last_failed_refresh is not None
            and self._clock() - self._last_failed_refresh < REFRESH_RETRY_DELAY
        ):
            if status.fetched_at is None:
                raise SdmxError(
                    "No How's Life? data is cached yet and the last download attempt failed. "
                    f"Try again in {REFRESH_RETRY_DELAY.seconds // 60} minutes."
                )
            return  # keep serving the stale copy rather than retrying on every read

        try:
            self.refresh()
        except SdmxError as exc:
            self._last_failed_refresh = self._clock()
            if status.fetched_at is None:
                raise  # nothing cached to fall back on
            log.warning(
                "Could not refresh the How's Life? cache (%s). Serving data fetched on %s.",
                exc,
                f"{status.fetched_at:%Y-%m-%d}",
            )

    def _open_fetcher(self) -> AbstractContextManager[Fetcher]:
        """The injected fetcher (tests), or a new SdmxClient that is closed after use."""
        return nullcontext(self._fetcher) if self._fetcher else SdmxClient()

    def _path(self, filename: str) -> Path:
        return self.directory / filename

    # Each file is written to a temporary name and then renamed over the old one. A rename is
    # atomic, so a crash mid-write can't leave a half-written file behind.
    def _write_parquet(self, filename: str, frame: pd.DataFrame) -> None:
        tmp = self._path(f"{filename}.tmp")
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, self._path(filename))

    def _write_json(self, filename: str, data: dict[str, Any]) -> None:
        tmp = self._path(f"{filename}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        os.replace(tmp, self._path(filename))
