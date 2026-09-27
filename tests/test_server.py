"""The MCP server end to end: an MCP client calls the tools as Claude would, against the real
(sliced) OECD responses in tests/fixtures (France, Mexico, Germany; life satisfaction and feeling
safe at night; 2018 onwards)."""

import json
import os
import subprocess
import sys

import pytest
from mcp import Client, StdioServerParameters

from wise_mcp.server import create_server
from wise_mcp.store import DataStore

pytestmark = pytest.mark.anyio

TOOLS = {
    "find_measures", "describe_measure", "compare_countries", "trend", "group_gaps",
    "country_profile", "better_life_36",
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
    assert "Gender gap in feeling safe at night" in text


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
    assert "briefing on France" in text and "country_profile" in text


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
