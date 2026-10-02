# wise_mcp
A prototype MCP server to query and interact with the OECD's `How's Life?` well-being database directly.

It isn't a general OECD data wrapper: it applies the How's Life? 2024 method to every answer.
OECD averages cover members only, and say how many. "Improving" means past the report's
threshold. Each value carries its year and flags. The data's quirks are handled, and listed in
[docs/data-specificities.md](docs/data-specificities.md). [evals/results.md](evals/results.md)
shows what that changes: 20 questions answered naively from the raw data and by wise_mcp,
checked against the report's published figures where it gives them.

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
| `suggest_charts` | Up to four charts that fit a question, each with a preview |
| `show_chart` | One chart full size, with its data as a table. In Claude Desktop, an interactive panel |
| `custom_chart` | A chart no template covers, from a Vega-Lite spec Claude writes (labelled as custom) |

All tools are read-only and answer from the local cache, so they never spend the OECD API's
rate limit.

In Claude Desktop, `show_chart` opens the chart as an interactive panel (an
[MCP App](https://github.com/modelcontextprotocol/ext-apps)). You can hover for exact values
and switch between the charts suggested for the question with tabs. The panel follows Desktop's
light or dark theme, and tells Claude which chart is on screen. Other clients get a PNG. The
panel runs offline: Vega is bundled in `src/wise_mcp/app/vendor`.

Chart templates: ranked bars or dots, trend lines, change arrows (every member), group gaps, a
tile grid map (every member against the OECD average), a country's trend grid and profile, and
the overall ranking. Each draws the method in: every value's year, flagged values, the OECD
average with its member count, which direction is better.

### A five-minute demo

1. *"How is France doing on well-being?"*: `country_trends` classes all 36 headline
   indicators in one call.
2. *"Chart trust in government in France and Germany"*: the interactive panel. Hover a point.
   Note the pooled periods (2014–16) and the dashed OECD average.
3. Switch the panel to **Change, all countries**, then ask *"which country improved most?"*.
   Claude answers about the chart on screen.
4. *"Show a map of homicide rates"*: the tile map. Lower is better, so the high rates show red.
5. *"What's the OECD average life expectancy?"*: then open `evals/results.md` to show that the
   naive route through the raw data gets it wrong, and the report's published figure.

## Evals

```bash
uv run python -m evals.run    # rewrite evals/results.md from the local cache
```

[evals/results.md](evals/results.md) compares a naive pandas analysis of the raw data with
wise_mcp on 20 questions, and with How's Life? 2024's published figures where there are some.
[evals/desktop-checklist.md](evals/desktop-checklist.md) is the same list for checking Claude's
answers by hand in Claude Desktop.

## R charts

[r/](r/) has two ggplot2 charts drawn from the same data: life satisfaction as a circular
barplot grouped by region, and an animated chart of household income against life expectancy,
2004-2023.

## Future work

- Controls in the chart panel to change countries and baseline year
- The report's rule for whether a gap between groups is widening or narrowing
- Bulgaria, when it joins the OECD (expected around the end of 2026)
- Evals with Claude answering from the raw data vs the MCP tools, graded automatically

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
