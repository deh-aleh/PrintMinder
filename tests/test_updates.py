import asyncio

import httpx

from app import updates


def test_parse_accepts_only_plain_releases():
    assert updates.parse("v1.2.3") == (1, 2, 3)
    assert updates.parse("1.10.0") == (1, 10, 0)
    for bad in ("1.2", "1.2.3-rc1", "latest", "", "v1.2.3; rm -rf /"):
        assert updates.parse(bad) is None


def test_newer_compares_numbers_not_text():
    assert updates.newer("1.10.0", "1.9.0")
    assert not updates.newer("1.2.0", "1.2.0")
    assert not updates.newer("1.1.0", "1.2.0")
    assert not updates.newer("2.0.0", "unknown")  # unknown installed version: say nothing


def _client(payload):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))


def test_fetch_latest_ignores_prereleases_and_bad_urls():
    ok = asyncio.run(updates.fetch_latest(_client({"tag_name": "v2.0.0", "html_url": "https://github.com/x/y/releases/v2.0.0"})))
    assert ok == {"version": "2.0.0", "url": "https://github.com/x/y/releases/v2.0.0"}
    assert asyncio.run(updates.fetch_latest(_client({"tag_name": "v2.0.0", "prerelease": True}))) is None
    assert asyncio.run(updates.fetch_latest(_client({"tag_name": "nightly"}))) is None
    odd = asyncio.run(updates.fetch_latest(_client({"tag_name": "v2.0.0", "html_url": "javascript:alert(1)"})))
    assert odd["url"] == ""
