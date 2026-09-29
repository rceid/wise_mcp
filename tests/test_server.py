"""The MCP server end to end: an MCP client calls the tools as Claude would, against the real
(sliced) OECD responses in tests/fixtures (France, Mexico, Germany; life satisfaction and feeling
safe at night; 2018 onwards)."""

import json
import os
import re
import subprocess
import sys

import pytest
from mcp import Client, StdioServerParameters
from mcp.client import advertise
from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID

from wise_mcp.server import create_server
from wise_mcp.store import DataStore

pytestmark = pytest.mark.anyio

TOOLS = {
    "find_measures", "describe_measure", "compare_countries", "trend", "group_gaps",
    "country_profile", "country_trends", "better_life_36", "suggest_charts", "show_chart",
    "chart_view",  # for the chart panel only (visibility: app)
    "custom_chart",
}  # fmt: skip


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(store):
    async with Client(create_server(store)) as client:
        yield client


async def call(client, tool, **arguments):
    result = await client.call_tool(tool, arguments)
    return result.is_error, result.content[0].text


async def test_tools_are_listed_as_read_only(client):
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == TOOLS
    assert all(tool.annotations.read_only_hint for tool in tools)
    assert all(tool.description for tool in tools)


async def test_claude_gets_the_house_rules(client):
    assert "Give the year of every figure" in client.instructions
    assert "Only the 38 OECD members" in client.instructions
    assert "call country_trends once" in client.instructions


async def test_find_measures(client):
    error, text = await call(client, "find_measures", query="life satisfaction")
    assert not error
    assert "| 11_1 | Life satisfaction |" in text


async def test_describe_measure(client):
    error, text = await call(client, "describe_measure", measure="10_2")
    assert not error
    assert "higher is better" in text and "at least 3.00" in text
    assert "3 OECD members, 2018-2025" in text


async def test_compare_countries(client):
    error, text = await call(client, "compare_countries", measure="11_1")
    assert not error
    assert "OECD 3 average" in text
    assert "| 1 | Mexico (MEX) | 2021 |" in text
    assert "Flagged values" in text


async def test_trend(client):
    error, text = await call(client, "trend", measure="11_1", since="2019")
    assert not error
    assert "change since 2019" in text
    # France has no 2019 value, so the baseline is its latest pre-pandemic year, 2018.
    assert "France (FRA) | 2018:" in text


async def test_group_gaps(client):
    error, text = await call(client, "group_gaps", measure="10_2", by="sex", countries=["FRA"])
    assert not error
    assert "| Female | Male | Better off | Female vs Male |" in text
    assert "| Male |" in text


async def test_country_profile_accepts_a_country_name(client):
    error, text = await call(client, "country_profile", country="france")
    assert not error
    assert "France (FRA)" in text
    assert "| Gender gap in feeling safe at night | 10_2 |" in text  # codes save lookups


async def test_better_life_36_with_weights(client):
    error, text = await call(client, "better_life_36", weights={"Safety": 2})
    assert not error
    assert "Better Life 36: current well-being" in text
    assert "Weights: Safety x2" in text


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("compare_countries", {"measure": "99_9"}, "Use find_measures"),
        ("country_profile", {"country": "Atlantis"}, "Unknown country"),
        ("better_life_36", {"weights": {"Happiness": 1}}, "Unknown current well-being dimension"),
        ("group_gaps", {"measure": "11_1", "by": "income"}, "input"),  # rejected by the schema
    ],
)
async def test_errors_reach_claude_with_a_useful_message(client, tool, arguments, message):
    error, text = await call(client, tool, **arguments)
    assert error
    assert message in text


async def test_every_result_cites_the_source(client):
    _, text = await call(client, "compare_countries", measure="11_1")
    assert text.endswith(
        "Source: OECD How's Life? well-being database, data fetched 2026-09-26. "
        "Methods: How's Life? 2024."
    )


async def test_data_is_downloaded_once_however_many_tools_are_called(client, fetcher):
    await call(client, "compare_countries", measure="11_1")
    await call(client, "trend", measure="11_1", since="2019")
    await call(client, "country_profile", country="FRA")
    assert sorted(fetcher.calls) == ["current", "future"]


async def test_country_briefing_prompt(client):
    prompt = await client.get_prompt("country_briefing", {"country": "France"})
    text = prompt.messages[0].content.text
    assert "briefing on France" in text
    assert "country_profile" in text and "country_trends" in text


async def test_the_server_command_speaks_mcp_over_stdio(tmp_path, fetcher):
    # Launches the real entry point as Claude Desktop does.
    DataStore(tmp_path, fetcher=fetcher).refresh()
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wise_mcp.server"],
        env={**os.environ, "WISE_MCP_CACHE_DIR": str(tmp_path)},
    )
    async with Client(server) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == TOOLS
        result = await client.call_tool("find_measures", {"query": "life satisfaction"})
        assert not result.is_error


def test_stdout_carries_only_protocol_messages(tmp_path, fetcher):
    # Claude Desktop reads the server's stdout as JSON-RPC, so a stray print() or log line there
    # breaks the connection. The MCP client above tolerates such lines, so check stdout directly.
    DataStore(tmp_path, fetcher=fetcher).refresh()
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    finished = subprocess.run(
        [sys.executable, "-m", "wise_mcp.server"],
        input=json.dumps(initialize) + "\n",  # the server exits when stdin closes
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "WISE_MCP_CACHE_DIR": str(tmp_path)},
    )
    lines = [line for line in finished.stdout.splitlines() if line.strip()]
    assert lines, finished.stderr
    messages = [json.loads(line) for line in lines]  # fails on anything that isn't JSON
    assert messages[0]["id"] == 1 and "result" in messages[0]


async def test_country_trends_answers_in_one_call(client):
    # The fixture data start in 2018, so compare with 2019.
    error, text = await call(client, "country_trends", country="France", since="2019")
    assert not error
    assert "France (FRA): How's Life? headline indicators, change since 2019" in text
    assert "Current well-being:" in text
    assert "| Safety | Gender gap in feeling safe at night | 10_2 | 2019: 8.51 |" in text


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("compare_countries", {"measure": "10_2"}),
        ("trend", {"measure": "10_2", "since": "2019"}),
        ("group_gaps", {"measure": "10_2", "by": "sex"}),
    ],
)
async def test_the_measure_note_is_shown_by_every_tool(client, tool, arguments):
    _, text = await call(client, tool, **arguments)
    assert "About this measure: The headline indicator is the gap between women and men" in text


async def test_suggest_charts_returns_ids_and_previews(client):
    result = await client.call_tool("suggest_charts", {"measure": "11_1", "countries": ["FRA"]})
    assert not result.is_error
    listing = result.content[0].text
    assert "id: `dot_plot?measure=11_1&highlight=FRA`" in listing
    images = [block for block in result.content if block.type == "image"]
    assert images and all(block.mime_type == "image/png" for block in images)
    assert result.content[-1].text.startswith("Source: OECD How's Life?")


async def test_show_chart_returns_the_image_and_its_table(client):
    result = await client.call_tool("show_chart", {"chart_id": "gap_dots?measure=10_2&by=sex"})
    assert not result.is_error
    assert [block.type for block in result.content] == ["image", "text", "text"]
    assert "| Female | Male |" in result.content[1].text


async def test_show_chart_explains_a_bad_id(client):
    error, text = await call(client, "show_chart", chart_id="pie_chart?measure=11_1")
    assert error and "Use suggest_charts" in text


# --- The chart panel (MCP App) ---------------------------------------------------------------

CHART = "trend_lines?measure=11_1&countries=FRA"


@pytest.fixture
async def desktop(store):
    """A client that supports MCP Apps, as Claude Desktop does."""
    apps = advertise(EXTENSION_ID, {"mimeTypes": [APP_MIME_TYPE]})
    async with Client(create_server(store), extensions=[apps]) as client:
        yield client


async def test_show_chart_opens_the_panel(client):
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert tools["show_chart"].meta["ui"]["resourceUri"] == "ui://wise-mcp/chart.html"
    assert tools["chart_view"].meta["ui"]["visibility"] == ["app"]  # hidden from Claude


async def test_with_the_panel_claude_gets_the_table_but_no_image(desktop):
    result = await desktop.call_tool("show_chart", {"chart_id": CHART})
    assert [block.type for block in result.content] == ["text"] * 3  # note, table, source
    assert "interactive panel" in result.content[0].text  # or Claude reports a missing image
    assert "| France (FRA) |" in result.content[1].text


async def test_chart_view_gives_the_panel_spec_table_and_tabs(desktop):
    result = await desktop.call_tool("chart_view", {"chart_id": CHART, "theme": "dark"})
    view = json.loads(result.content[0].text)
    assert view["id"] == CHART
    assert view["spec"]["config"]["background"] == "#1a1a19"
    assert view["table"].rstrip().endswith("Methods: How's Life? 2024.")
    tabs = [tab["id"] for tab in view["tabs"]]
    assert CHART in tabs and len(tabs) > 1
    assert all(tab["label"] for tab in view["tabs"])


async def test_the_panel_is_self_contained(client):
    (page,) = (await client.read_resource("ui://wise-mcp/chart.html")).contents
    assert page.mime_type == APP_MIME_TYPE
    # Vega is inlined: the host's default CSP allows no outside scripts, and the demo is offline.
    assert not re.search(r"<script[^>]*\bsrc=", page.text)
    assert "vegaInterpreter" in page.text  # expressions without eval, which the CSP forbids
    assert page.text.count("<script") == page.text.count("</script>")
