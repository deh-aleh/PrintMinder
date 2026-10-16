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


def test_a_beta_is_never_offered_but_an_installed_beta_is_told_about_the_final_release():
    for beta in ("v1.2.3-beta.1", "1.2.3b1"):
        assert updates.parse(beta) is None                           # never offered
    assert updates.newer("1.2.3", "1.2.3b1") and updates.newer("1.2.3", "1.2.3-beta.4")   # the final release follows its betas
    assert updates.newer("1.2.4", "1.2.3b1") and not updates.newer("1.2.2", "1.2.3b1")
    assert not updates.newer("1.2.3", "1.2.3")
    assert not updates.newer("1.2.3", "1.2.3bx")                      # junk installed version: say nothing


def test_a_pre_release_on_github_is_not_offered():
    assert asyncio.run(updates.fetch_latest(_client({"tag_name": "v1.2.3-beta.1", "prerelease": True, "html_url": "https://x"}))) is None


def test_an_installed_beta_can_update_from_the_portal_within_its_major(monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "app_version", lambda: "1.2.3b1")
    monkeypatch.setattr(updates, "_dir", lambda: tmp_path)
    updates.write_request("1.2.3", "root", "b")
    import pytest
    with pytest.raises(ValueError):
        updates.write_request("2.0.0", "root", "b")
