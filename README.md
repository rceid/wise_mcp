# wise_mcp
A prototype MCP server to query and interact with the OECD's `How's Life?` well-being database directly

## Use it in Claude Desktop

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude
Desktop. Use the full path to `uv` (`which uv`): Claude Desktop doesn't see your shell's `PATH`.

```json
{
  "mcpServers": {
    "wise-mcp": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/path/to/wise_mcp", "run", "wise-mcp"]
    }
  }
}
```

Then ask, for example: *"How does life satisfaction in France compare with the OECD average?"*,
*"Is life expectancy in the US improving?"* or *"Where is the gender gap in feeling safe at night
widest?"*. The **Country well-being briefing** prompt writes a How's Life?-style country note.

| Tool | What it answers |
|---|---|
| `find_measures` | Which measure code covers a topic ("NEET", "trust") |
| `describe_measure` | Unit, which direction is better, threshold for meaningful change, coverage |
| `compare_countries` | OECD members ranked on one measure, against the OECD average |
| `trend` | Improving, deteriorating or no clear change since ~2010 or since 2019 |
| `group_gaps` | Women vs men, age groups or education levels |
| `country_profile` | A country's 36 headline indicators: strengths, weaknesses, rank |
| `country_trends` | All 36 headline indicators for one country: improving or not, in one call |
| `better_life_36` | Overall well-being score, with optional weights per dimension |

All tools are read-only and answer from the local cache, so they never spend the OECD API's
rate limit.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                      # install dependencies
uv run pytest                # offline tests (never call the OECD API)
uv run pytest -m live        # checks against the real API (2 requests)
uv run ruff check && uv run ruff format --check
```

### Data cache

The whole How's Life? database is downloaded once (2 API requests) and kept locally, because the
OECD API allows only about 60 requests per hour. It refreshes itself after 30 days.

```bash
uv run wise-mcp-cache status     # what's cached, and when it was fetched
uv run wise-mcp-cache refresh    # download everything again, e.g. before a demo
```

The cache lives in the OS cache folder (`~/Library/Caches/wise-mcp` on macOS). Set
`WISE_MCP_CACHE_DIR` to use another location.

### Analysis

`wise_mcp.analysis` answers questions the way How's Life? 2024 does: OECD averages over members
only, change judged against each indicator's threshold, gaps as ratios to the population average.
Every result carries chart-ready tables and plain-language caveats. The quirks in the data that
make this necessary are listed in [docs/data-specificities.md](docs/data-specificities.md).

```python
from wise_mcp.analysis import WellbeingData, compare_countries, country_profile, trend
from wise_mcp.store import DataStore

data = WellbeingData.from_store(DataStore())
data.find_measures("life satisfaction")  # look up measure codes
result = compare_countries(data, "11_1")  # ranking, OECD average, caveats
trend(data, "11_1", ["FRA", "CAN"]).changes  # improving / deteriorating since ~2010
country_profile(data, "MEX").weaknesses  # headline indicators in the bottom third
```
