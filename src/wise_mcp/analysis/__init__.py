"""Analysis of the How's Life? data, following the methods of How's Life? 2024.

Every function takes a `WellbeingData` and returns a result with tidy, chart-ready tables plus
plain-language caveats, so the MCP tools and charts built on top never recompute anything.
"""

from wise_mcp.analysis.data import AnalysisError, WellbeingData, goodness
from wise_mcp.analysis.gaps import GroupGaps, group_gaps
from wise_mcp.analysis.headlines import (
    CountryTrends,
    Index,
    Profile,
    country_profile,
    country_trends,
    headline_scores,
    wellbeing_index,
)
from wise_mcp.analysis.snapshot import (
    Comparison,
    OecdAverage,
    compare_countries,
    latest,
    oecd_average,
)
from wise_mcp.analysis.trends import Trend, assess, trend

__all__ = [
    "AnalysisError",
    "Comparison",
    "CountryTrends",
    "GroupGaps",
    "Index",
    "OecdAverage",
    "Profile",
    "Trend",
    "WellbeingData",
    "assess",
    "compare_countries",
    "country_profile",
    "country_trends",
    "goodness",
    "group_gaps",
    "headline_scores",
    "latest",
    "oecd_average",
    "trend",
    "wellbeing_index",
]
