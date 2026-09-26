"""`wise-mcp-cache status` / `wise-mcp-cache refresh`: inspect or warm the local cache.

Handy before a demo: refresh once on good wifi and the server can answer everything offline.
"""

import argparse
import logging
import sys

from wise_mcp.config import CACHE_TTL
from wise_mcp.sdmx import SdmxError
from wise_mcp.store import CacheStatus, DataStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wise-mcp-cache", description="Manage the local copy of the How's Life? database."
    )
    parser.add_argument(
        "command",
        choices=["status", "refresh"],
        help="status: show what's cached. refresh: download everything again (2 API requests).",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    store = DataStore()
    if args.command == "refresh":
        try:
            store.refresh()
        except SdmxError as exc:
            print(f"Refresh failed: {exc}", file=sys.stderr)
            return 1
    print(format_status(store.status()))
    return 0


def format_status(status: CacheStatus) -> str:
    lines = [f"Cache: {status.directory}"]
    if status.fetched_at is None:
        lines.append("No data cached yet. Run `wise-mcp-cache refresh` to download it.")
        return "\n".join(lines)

    freshness = "stale, will refresh on next read" if status.is_stale else "fresh"
    lines.append(
        f"Fetched: {status.fetched_at:%Y-%m-%d %H:%M} UTC "
        f"({freshness}; refreshes after {CACHE_TTL.days} days)"
    )
    for name, info in status.dataflows.items():
        lines.append(f"  {name}: {info['rows']:,} rows, {info['name']} ({info['structure_id']})")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
