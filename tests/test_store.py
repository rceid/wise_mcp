from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pandas as pd
import pytest

from wise_mcp.config import CACHE_TTL, REFRESH_RETRY_DELAY
from wise_mcp.sdmx import RateLimitError, SdmxError, parse_labelled_csv
from wise_mcp.store import DataStore

CACHE_FILES = {"current.parquet", "future.parquet", "labels.json", "metadata.json"}
PAST_TTL = CACHE_TTL + timedelta(minutes=1)


class TestFirstUse:
    def test_first_read_downloads_both_dataflows(self, store, fetcher):
        observations = store.observations("current")

        assert sorted(fetcher.calls) == ["current", "future"]
        assert len(observations) == 288
        assert {p.name for p in store.directory.iterdir()} == CACHE_FILES

    def test_nothing_cached_and_api_unavailable_raises(self, store, fetcher):
        fetcher.fail_all(RateLimitError(None))
        with pytest.raises(RateLimitError):
            store.observations("current")

    def test_unknown_dataflow(self, store):
        with pytest.raises(KeyError, match="expected one of"):
            store.observations("past")


class TestRateLimitProtection:
    def test_fresh_cache_makes_no_api_calls(self, tmp_path, fetcher, clock):
        DataStore(tmp_path, fetcher=fetcher, clock=clock).refresh()
        fetcher.calls.clear()
        clock.advance(CACHE_TTL - timedelta(hours=1))

        # A new store reads from disk, as it would after the MCP server restarts.
        store = DataStore(tmp_path, fetcher=fetcher, clock=clock)
        store.observations("current")
        store.observations("future")
        store.labels()

        assert fetcher.calls == []

    def test_stale_cache_refreshes_once(self, store, fetcher, clock):
        store.refresh()
        fetcher.calls.clear()
        clock.advance(PAST_TTL)

        store.observations("current")
        store.observations("future")
        store.labels()

        assert sorted(fetcher.calls) == ["current", "future"]
        assert not store.status().is_stale

    def test_stale_cache_is_served_when_refresh_fails(self, store, fetcher, clock, caplog):
        store.refresh()
        clock.advance(PAST_TTL)
        fetcher.fail_all(RateLimitError("3600"))

        observations = store.observations("current")

        assert len(observations) == 288
        assert "Serving data fetched on 2026-09-26" in caplog.text

    def test_failed_refresh_is_not_retried_until_delay_passes(self, store, fetcher, clock):
        store.refresh()
        clock.advance(PAST_TTL)
        fetcher.fail_all(RateLimitError(None))
        store.observations("current")  # this refresh attempt fails
        attempts = len(fetcher.calls)

        clock.advance(REFRESH_RETRY_DELAY - timedelta(minutes=1))
        store.observations("current")
        store.labels()
        assert len(fetcher.calls) == attempts

        clock.advance(timedelta(minutes=2))
        fetcher.errors.clear()
        store.observations("current")
        assert len(fetcher.calls) > attempts
        assert not store.status().is_stale

    def test_failed_first_download_is_not_retried_until_delay_passes(self, store, fetcher):
        fetcher.fail_all(RateLimitError(None))
        with pytest.raises(RateLimitError):
            store.observations("current")
        attempts = len(fetcher.calls)

        with pytest.raises(SdmxError, match="last download attempt failed"):
            store.observations("current")
        assert len(fetcher.calls) == attempts

    def test_parallel_reads_trigger_a_single_refresh(self, store, fetcher):
        fetcher.delay = 0.05  # long enough for the threads to overlap
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: store.observations("current"), range(4)))

        assert sorted(fetcher.calls) == ["current", "future"]


class TestRefresh:
    def test_failed_refresh_leaves_previous_cache_intact(self, store, fetcher, clock):
        store.refresh()
        before = {p.name: p.read_bytes() for p in store.directory.iterdir()}
        clock.advance(PAST_TTL)
        fetcher.errors["future"] = RateLimitError(None)  # "current" succeeds, "future" fails

        with pytest.raises(RateLimitError):
            store.refresh()

        after = {p.name: p.read_bytes() for p in store.directory.iterdir()}
        assert after == before

    def test_cache_round_trip_preserves_data_and_types(self, store, current_csv):
        cached = store.observations("current")
        parsed = parse_labelled_csv(current_csv).observations
        pd.testing.assert_frame_equal(cached, parsed)

    def test_labels_combine_both_dataflows(self, store):
        labels = store.labels()
        assert labels["domain"]["HSL_11"] == "Subjective well-being"
        assert labels["domain"]["HSL_12"] == "Natural capital"
        assert labels["measure"]["12_14"] == "Material footprint per capita"

    def test_status_reports_fetch_time_rows_and_version(self, store, clock):
        assert store.status().fetched_at is None

        store.refresh()
        status = store.status()

        assert status.fetched_at == clock.now
        assert not status.is_stale
        assert status.dataflows["current"]["rows"] == 288
        assert status.dataflows["future"]["structure_id"].startswith(
            "OECD.WISE.WDP:DSD_HSL@DF_HSL_FWB("
        )

    def test_failed_refresh_keeps_data_already_in_memory(self, store, fetcher):
        assert len(store.observations("current")) == 288
        fetcher.errors["current"] = SdmxError("boom")
        with pytest.raises(SdmxError):
            store.refresh()
        assert len(store.observations("current")) == 288
