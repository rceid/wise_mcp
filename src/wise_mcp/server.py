"""The MCP server: How's Life? well-being analysis as tools Claude can call.

Run it with `wise-mcp` (stdio transport, as Claude Desktop expects). Every tool is read-only and
answers from the local cache, so tool calls don't spend the OECD API's rate limit (see store.py).
Each tool is a thin wrapper: the analysis package does the work, render.py writes the Markdown.
"""

import json
import logging
import sys
from collections.abc import Callable
from importlib.metadata import version
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.apps import Apps, client_supports_apps
from mcp.server.mcpserver import Context, Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from wise_mcp import analysis, app, render
from wise_mcp.analysis import AnalysisError, WellbeingData
from wise_mcp.analysis.headlines import INDEX_NAME
from wise_mcp.charts import catalog, export
from wise_mcp.sdmx import SdmxError
from wise_mcp.store import DataStore

# Sent to Claude when it connects: the rules every answer should follow.
INSTRUCTIONS = """\
These tools answer questions with the OECD How's Life? well-being database, using the methods of \
the How's Life? 2024 report. Follow these rules in every answer:
- Look up measure codes with find_measures (or describe_measure); never guess them.
- For how a country is doing over time, call country_trends once rather than trend for each \
indicator. Use trend for one indicator across several countries.
- Give the year of every figure: countries' latest years often differ.
- The OECD average is a simple mean over OECD members with data. Say how many when it's fewer \
than 38 (e.g. "OECD 34").
- "Improving" and "deteriorating" follow How's Life? thresholds for meaningful change; smaller \
changes are "no clear change". Don't describe them as improvements.
- Pass on the caveats the tools return, such as series breaks, estimates and differing years.
- Only the 38 OECD members are covered.
- Cite the source line at the end of each tool result.
- When a chart would help, call suggest_charts, then show_chart with the chosen chart's id."""

# Opens show_chart's result when the chart is in the interactive panel, not in the result.
PANEL_NOTE = (
    "The chart is shown to the user as an interactive panel (hover for values, tabs for the "
    "other suggested charts), so no image comes with this result. Its data:"
)

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)

MeasureCode = Annotated[
    str,
    Field(description='Measure code such as "11_1" (life satisfaction). Look it up with '
          "find_measures."),
]  # fmt: skip
Countries = Annotated[
    list[str] | None,
    Field(description='Countries as ISO codes ("FRA") or English names ("France"). Leave out '
          "for all OECD members."),
]  # fmt: skip


class Source:
    """The data behind every tool: loaded on first use, reloaded after the cache refreshes."""

    def __init__(self, store: DataStore) -> None:
        self.store = store
        self._data: WellbeingData | None = None
        self._fetched_at = None

    def data(self) -> WellbeingData:
        status = self.store.status()
        if self._data is None or status.is_stale or status.fetched_at != self._fetched_at:
            self._data = WellbeingData.from_store(self.store)
            self._fetched_at = self.store.status().fetched_at
        return self._data

    def citation(self) -> str:
        fetched = self.store.status().fetched_at
        when = f", data fetched {fetched:%Y-%m-%d}" if fetched else ""
        return f"Source: OECD How's Life? well-being database{when}. Methods: How's Life? 2024."


def create_server(store: DataStore | None = None) -> MCPServer:
    source = Source(store or DataStore())

    def answer(build: Callable[[WellbeingData], Any], cite: bool = True) -> Any:
        """Run one analysis, returning Markdown or a list of text and images, with the source
        at the end (unless `cite` is false). Expected failures become ToolErrors, whose message
        Claude sees (any other exception reaches it only as "Error executing tool")."""
        try:
            result = build(source.data())
        except AnalysisError as exc:
            raise ToolError(str(exc)) from exc
        except SdmxError as exc:
            raise ToolError(f"The How's Life? data couldn't be loaded: {exc}") from exc
        if not cite:
            return result
        if isinstance(result, str):
            return render.join(result, source.citation())
        return [*result, source.citation()]

    server = MCPServer(
        "wise-mcp",
        title="How's Life? well-being data (OECD)",
        instructions=INSTRUCTIONS,
        version=version("wise-mcp"),
        extensions=[_chart_panel(source, answer)],
    )

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def find_measures(
        query: Annotated[str, Field(description='Topic words, e.g. "life satisfaction", "NEET"')],
    ) -> str:
        """Find How's Life? measure codes by topic. Use this first: every other tool needs a
        measure code such as "11_1". Searches indicator names, OECD labels and dimensions."""
        return answer(lambda data: render.measures(data.find_measures(query), query))

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def describe_measure(measure: MeasureCode) -> str:
        """What a measure is: its unit, whether higher or lower is better, the threshold for a
        meaningful change, whether it's a headline indicator, and which countries, years and
        breakdowns (by sex, age, education) have data."""
        return answer(
            lambda data: render.description(data.describe(measure), data.coverage(measure))
        )

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def compare_countries(measure: MeasureCode, countries: Countries = None) -> str:
        """Rank OECD countries on one measure using each country's latest value, best first,
        against the OECD average. Flags values from different years, series breaks and
        estimates."""
        return answer(
            lambda data: render.comparison(analysis.compare_countries(data, measure, countries))
        )

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def trend(
        measure: MeasureCode,
        countries: Countries = None,
        since: Annotated[
            str,
            Field(
                description='"2010" for the medium term (the How\'s Life? default), "2019" for '
                "the period since the pandemic, or any year."
            ),
        ] = "2010",  # fmt: skip
    ) -> str:
        """Is life getting better? Change from a baseline year to the latest year, classed as
        improving, deteriorating or no clear change with How's Life? thresholds, per country and
        for the OECD average."""
        return answer(
            lambda data: render.trend(analysis.trend(data, measure, countries, since=since))
        )

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def group_gaps(
        measure: MeasureCode,
        by: Annotated[
            Literal["sex", "age", "education"], Field(description="Which groups to compare")
        ] = "sex",
        countries: Countries = None,
    ) -> str:
        """Who is better off? Compares women and men, age groups or education levels on one
        measure, as ratios to the population average (How's Life? 2024, Chapter 3). Use
        describe_measure to see which breakdowns a measure has."""
        return answer(
            lambda data: render.gaps(analysis.group_gaps(data, measure, by=by, countries=countries))
        )

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def country_profile(
        country: Annotated[str, Field(description='ISO code ("FRA") or English name ("France")')],
    ) -> str:
        """A country's How's Life? headline indicators (24 for current well-being, 12 for future
        well-being) against the OECD average: rank among members, strengths (top third) and
        weaknesses (bottom third), and its overall Better Life 36 scores."""
        return answer(
            lambda data: render.profile(analysis.country_profile(data, country), INDEX_NAME)
        )

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def country_trends(
        country: Annotated[str, Field(description='ISO code ("FRA") or English name ("France")')],
        since: Annotated[
            str,
            Field(
                description='"2010" for the medium term (the How\'s Life? default), "2019" for '
                "the period since the pandemic, or any year."
            ),
        ] = "2010",  # fmt: skip
    ) -> str:
        """Is life getting better in one country? All 36 How's Life? headline indicators classed
        as improving, deteriorating or no clear change since a baseline year, next to the OECD
        average's change, in one call (How's Life? 2024, Chapter 4). Use this rather than calling
        trend indicator by indicator."""
        return answer(
            lambda data: render.country_trends(analysis.country_trends(data, country, since=since))
        )

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def better_life_36(
        weights: Annotated[
            dict[str, float] | None,
            Field(
                description='Weight per dimension, by name or number, e.g. {"Health": 5, '
                '"Income and wealth": 0}. Unlisted dimensions keep weight 1; 0 drops one. '
                "Leave out for equal weights."
            ),
        ] = None,  # fmt: skip
        kind: Annotated[
            Literal["current", "future"],
            Field(description="current: 11 dimensions of well-being today; future: 4 capitals"),
        ] = "current",
    ) -> str:
        """Rank OECD members by an overall well-being score (0-1) over the How's Life? headline
        indicators, with optional weights per dimension, like the Better Life Index. Equal
        weights reproduce the How's Life? 2024 method."""
        return answer(lambda data: render.index(analysis.wellbeing_index(data, weights, kind=kind)))

    @server.tool(annotations=READ_ONLY, structured_output=False)
    def suggest_charts(
        measure: Annotated[
            str | None, Field(description='Measure code, e.g. "11_1", if the question is about one')
        ] = None,
        country: Annotated[
            str | None, Field(description="A country, if the question is about one country")
        ] = None,
        countries: Countries = None,
        since: Annotated[
            str, Field(description='Baseline for charts of change: "2010", "2019" or any year')
        ] = "2010",
    ) -> list[Any]:
        """Suggest up to four charts that fit a question, each with a small preview image.
        Pass what the question is about: a measure, a country, or a measure plus the countries
        of interest (they get highlighted). Then call show_chart with the chosen chart's id."""

        def build(data: WellbeingData) -> list[Any]:
            lines = ["Charts that fit, best first. Call show_chart with an id to draw one.", ""]
            previews: list[Any] = []
            for option in catalog.suggest(data, measure, country, countries, since):
                try:
                    drawing = catalog.draw(data, option.id)
                except AnalysisError:
                    continue  # e.g. no country has data for the period: don't offer it
                number = len(previews) // 2 + 1
                lines.append(
                    f"{number}. **{option.title}**  \n   id: `{option.id}`  \n   {option.why}"
                )
                previews += [
                    f"Preview {number}: {option.title}",
                    Image(data=export.png(drawing.chart, export.THUMBNAIL_SCALE), format="png"),
                ]
            if not previews:
                raise AnalysisError("No chart fits: there isn't enough data for this question.")
            return ["\n".join(lines), *previews]

        return answer(build)

    @server.prompt(title="Country well-being briefing")
    def country_briefing(
        country: Annotated[str, Field(description="Country name or ISO code, e.g. France")],
    ) -> str:
        """A How's Life?-style briefing on one country's well-being."""
        return (
            f"Write a short well-being briefing on {country}, in the style of a How's Life? 2024 "
            "country note.\n"
            f"1. Call country_profile for {country}.\n"
            f"2. Call country_trends for {country} to see which indicators have improved or "
            "worsened since around 2010.\n"
            "3. Call group_gaps by sex for feeling safe at night (10_2).\n"
            "Structure it as: overall position (Better Life 36 ranks), strengths, weaknesses, "
            "trends, and one inequality. Give the year of every figure, compare with the OECD "
            "average, and pass on the tools' caveats. Keep it under 300 words."
        )

    return server


def _chart_panel(source: Source, answer: Callable[..., Any]) -> Apps:
    """show_chart as an MCP App: in clients that support it (Claude Desktop) the chart opens as
    an interactive panel, and Claude gets only the table; elsewhere it's a PNG and the table.

    The panel draws with the app-only tool chart_view, so the Vega-Lite spec (tens of KB of data)
    never enters Claude's context."""
    apps = Apps()

    @apps.tool(resource_uri=app.URI, annotations=READ_ONLY, structured_output=False)
    def show_chart(
        chart_id: Annotated[
            str, Field(description='An id from suggest_charts, e.g. "dot_plot?measure=11_1"')
        ],
        ctx: Context,
    ) -> list[Any]:
        """Draw one chart full size from an id that suggest_charts returned, with the same data
        as a table so every value can be read without the picture. In Claude Desktop it opens as
        an interactive panel: hover for values, tabs for the other suggested charts."""
        interactive = client_supports_apps(ctx)

        def build(data: WellbeingData) -> list[Any]:
            drawing = catalog.draw(data, chart_id)
            if interactive:
                # Without this, Claude sees no image and reports the chart as missing.
                return [PANEL_NOTE, drawing.table]
            return [Image(data=export.png(drawing.chart), format="png"), drawing.table]

        return answer(build)

    @apps.tool(
        resource_uri=app.URI, visibility=["app"], annotations=READ_ONLY, structured_output=False
    )
    def chart_view(chart_id: str, theme: str = "light") -> str:
        """For the chart panel: a chart's Vega-Lite spec (light or dark), its table, and the
        other charts suggested for the same question, as JSON."""

        def build(data: WellbeingData) -> str:
            drawing = catalog.draw(data, chart_id)
            options = catalog.related(data, chart_id)
            titles = {o.id: o.title for o in options}
            return json.dumps(
                {
                    "id": chart_id,
                    "title": titles.get(chart_id, catalog.tab_label(chart_id)),
                    "spec": export.spec(drawing.chart, "dark" if theme == "dark" else "light"),
                    "table": render.join(drawing.table, source.citation()),
                    "tabs": [
                        {"id": o.id, "label": catalog.tab_label(o.id), "title": o.title}
                        for o in options
                    ],
                }
            )

        return answer(build, cite=False)  # the table inside already ends with the source

    apps.add_html_resource(
        app.URI, app.chart_html(), title="How's Life? chart", prefers_border=True
    )
    return apps


def main() -> None:
    # stdout carries the MCP protocol itself, so all logging must go to stderr.
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    create_server().run()


if __name__ == "__main__":
    main()
