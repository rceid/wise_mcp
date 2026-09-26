import respx

from wise_mcp.cli import main
from wise_mcp.store import DataStore


def test_status_with_empty_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WISE_MCP_CACHE_DIR", str(tmp_path))

    assert main(["status"]) == 0
    assert "No data cached yet" in capsys.readouterr().out


def test_status_after_refresh(tmp_path, monkeypatch, capsys, fetcher):
    monkeypatch.setenv("WISE_MCP_CACHE_DIR", str(tmp_path))
    DataStore(tmp_path, fetcher=fetcher).refresh()

    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "current: 288 rows, Current well-being" in out
    assert "(fresh; refreshes after 30 days)" in out


@respx.mock
def test_refresh_failure_exits_with_error(tmp_path, monkeypatch, capsys):
    # Goes through the real SdmxClient, with the HTTP layer faked to answer "rate limited".
    monkeypatch.setenv("WISE_MCP_CACHE_DIR", str(tmp_path))
    respx.get(url__startswith="https://sdmx.oecd.org/").respond(429)

    assert main(["refresh"]) == 1
    assert "rate limit" in capsys.readouterr().err
