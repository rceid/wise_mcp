"""Where the How's Life? data comes from and where the local copy lives."""

import os
from datetime import timedelta
from pathlib import Path

from platformdirs import user_cache_path

SDMX_BASE_URL = "https://sdmx.oecd.org/public/rest"

# How's Life? is published by the WISE Centre's well-being data agency as six dataflows that
# share one data structure (DSD_HSL). The by-age, by-sex, by-education and vertical-inequality
# dataflows are filtered views of "current" (every one of their rows is in it, with the same
# value), so these two downloads cover the whole database.
AGENCY_ID = "OECD.WISE.WDP"
DATAFLOWS = {
    "current": "DSD_HSL@DF_HSL_CWB",  # Current well-being: 11 dimensions, e.g. health, safety
    "future": "DSD_HSL@DF_HSL_FWB",  # Resources for future well-being: 4 capitals
}

# How's Life? is revised once or twice a year, so a week-old copy is effectively current.
CACHE_TTL = timedelta(days=7)

# After a failed refresh (rate limited, offline), wait this long before trying again rather
# than retrying on every read and spending more of the ~60 requests/hour budget.
REFRESH_RETRY_DELAY = timedelta(minutes=15)


def cache_dir() -> Path:
    """The OS cache folder (~/Library/Caches/wise-mcp on macOS) unless WISE_MCP_CACHE_DIR is set."""
    override = os.environ.get("WISE_MCP_CACHE_DIR")
    return Path(override) if override else user_cache_path("wise-mcp")
