"""TDD tests for utils/jd_fetch.py — plan: plans/jd-fetcher.md.

Every test is stubbed: zero network, zero browser (plan §4).
"""
import json
from types import SimpleNamespace

import pytest
import requests

from jd_fetch import (
    AshbyBoardSource, FetchBlocked, GreenhouseSource, JsonLdSource, StaticSource,
    WebpageFetcher, get_page, main, render_markdown,
)


class StubSource:
    """Inert PageSource stub: preset supports flag, preset extract result/exc."""

    def __init__(self, supports=False, result=None, exc=None):
        self._supports, self.result, self.exc = supports, result, exc
        self.extract_calls = []

    def supports(self, url, body):
        return self._supports

    def extract(self, url, body):
        self.extract_calls.append((url, body))
        if self.exc is not None:
            raise self.exc
        return self.result


def test_fetch_returns_markdown_with_title_header():
    src = StubSource(supports=True, result=("Eng Manager - EU", "<p>Write <b>go</b> code.</p>"))
    fetcher = WebpageFetcher([src], page_get=lambda url: "<html/>")

    md = fetcher.fetch("https://example.com/job")

    assert md.startswith("# Eng Manager - EU")
    assert "Write **go** code." in md
    assert src.extract_calls == [("https://example.com/job", "<html/>")]


def test_render_markdown_without_title_has_no_header():
    assert render_markdown(None, "<p>hi</p>").strip() == "hi"


def test_render_markdown_unescapes_entity_encoded_html():
    """Board APIs sometimes store fully entity-encoded content (live: vercel greenhouse)."""
    md = render_markdown("T", "&lt;p&gt;Hi &lt;b&gt;there&lt;/b&gt;&lt;/p&gt;")

    assert "Hi **there**" in md
    assert "<p>" not in md


def test_render_markdown_leaves_real_html_alone():
    md = render_markdown(None, "<p>a &lt; b</p>")

    assert "a < b" in md


LD_PAGE = (
    '<html><head>'
    '<script type="application/ld+json">{"@type":"Organization","name":"Co"}</script>'
    '<script type="application/ld+json">'
    '{"@type":"JobPosting","title":"Pilot Job","description":"<p>Do <b>things</b>.</p>"}'
    '</script></head><body>shell</body></html>'
)


def test_jsonld_source_matches_and_extracts_jobposting():
    src = JsonLdSource()
    url = "https://jobs.ashbyhq.com/ashby/abc"

    assert src.supports(url, LD_PAGE)
    assert src.extract(url, LD_PAGE) == ("Pilot Job", "<p>Do <b>things</b>.</p>")


def test_jsonld_source_rejects_page_without_jobposting():
    body = "<html><body>shell</body></html>"

    assert not JsonLdSource().supports("https://x/job", body)
    with pytest.raises(FetchBlocked) as exc_info:
        JsonLdSource().extract("https://x/job", body)
    assert exc_info.value.status == 200


def test_jsonld_source_requires_body():
    assert not JsonLdSource().supports("https://x/job", None)


def test_jsonld_source_handles_type_list_array_toplevel_and_extra_attrs():
    body = (
        '<script type="application/ld+json">[{"@type":"BreadcrumbList"}]</script>'
        '<script data-extra="1" type="application/ld+json">'
        '{"@type":["JobPosting"],"title":"T","description":"<p>D</p>"}</script>'
    )
    src = JsonLdSource()

    assert src.supports("https://x/job", body)
    assert src.extract("https://x/job", body) == ("T", "<p>D</p>")


BOARD = {"jobs": [
    {"id": "abc-1", "title": "Board Job", "descriptionHtml": "<p>board desc</p>"},
    {"id": "def-2", "title": "Other Job", "descriptionHtml": "<p>other</p>"},
]}


def test_board_source_is_url_decidable_without_body():
    src = AshbyBoardSource()

    assert src.supports("https://jobs.ashbyhq.com/ashby/abc-1", None)
    assert not src.supports("https://example.com/careers/123", "<html/>")


def test_board_source_extract_matches_job_id(monkeypatch):
    seen = {}
    def fake_get(url, **kw):
        seen["url"] = url
        return SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode())
    monkeypatch.setattr(requests, "get", fake_get)

    title, html = AshbyBoardSource().extract("https://jobs.ashbyhq.com/ashby/abc-1", None)

    assert (title, html) == ("Board Job", "<p>board desc</p>")
    assert seen["url"] == "https://api.ashbyhq.com/posting-api/job-board/ashby"


def test_board_source_ignores_query_string_in_job_id(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))

    title, _ = AshbyBoardSource().extract(
        "https://jobs.ashbyhq.com/ashby/abc-1?utm_source=x", None)

    assert title == "Board Job"


def test_board_source_blocks_when_id_missing(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))

    with pytest.raises(FetchBlocked):
        AshbyBoardSource().extract(
            "https://jobs.ashbyhq.com/ashby/00000000-0000-0000-0000-000000000000", None)


GH_JOB = {"title": "Software Engineer, eve", "content": "<p>eve desc</p>"}


def test_greenhouse_source_is_url_decidable_without_body():
    src = GreenhouseSource()

    assert src.supports("https://job-boards.greenhouse.io/vercel/jobs/6098390004", None)
    assert src.supports("https://boards.greenhouse.io/vercel/jobs/6098390004", None)
    assert not src.supports("https://example.com/careers/123", "<html/>")


def test_greenhouse_source_extract_returns_title_and_content(monkeypatch):
    seen = {}
    def fake_get(url, **kw):
        seen["url"] = url
        return SimpleNamespace(status_code=200, content=json.dumps(GH_JOB).encode())
    monkeypatch.setattr(requests, "get", fake_get)

    title, html = GreenhouseSource().extract(
        "https://job-boards.greenhouse.io/vercel/jobs/6098390004", None)

    assert (title, html) == ("Software Engineer, eve", "<p>eve desc</p>")
    assert seen["url"] == "https://boards-api.greenhouse.io/v1/boards/vercel/jobs/6098390004"


def test_greenhouse_source_blocks_on_api_failure(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=404, content=b"not found"))

    with pytest.raises(FetchBlocked) as exc_info:
        GreenhouseSource().extract("https://job-boards.greenhouse.io/x/jobs/1", None)

    assert exc_info.value.status == 404


def test_greenhouse_source_blocks_on_missing_content(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=b'{"title":"T"}'))

    with pytest.raises(FetchBlocked):
        GreenhouseSource().extract("https://job-boards.greenhouse.io/x/jobs/1", None)


def test_get_page_decodes_unlabelled_utf8(monkeypatch):
    """No charset header → requests guesses ISO-8859-1; the bytes are really UTF-8."""
    resp = SimpleNamespace(
        status_code=200, content="Cisco’s".encode("utf-8"), text="Ciscoâs")
    monkeypatch.setattr(requests, "get", lambda url, **kw: resp)

    assert get_page("https://x/job") == "Cisco’s"


def test_static_source_serves_ssr_body_but_never_ashby_or_bodiless():
    src = StaticSource()

    assert src.supports("https://example.com/job", "<p>x</p>")
    assert src.extract("https://example.com/job", "<p>x</p>") == (None, "<p>x</p>")
    assert not src.supports("https://jobs.ashbyhq.com/ashby/abc", "<html/>")
    assert not src.supports("https://example.com/job", None)


def test_routing_prefers_jsonld_over_ashby_api(monkeypatch):
    """Ashby page WITH ld+json: JsonLd wins, the board api is never called."""
    def boom(url, **kw):
        raise AssertionError(f"unexpected GET {url}")
    monkeypatch.setattr(requests, "get", boom)
    fetcher = WebpageFetcher(
        [JsonLdSource(), AshbyBoardSource(), GreenhouseSource(), StaticSource()],
        page_get=lambda url: LD_PAGE)

    md = fetcher.fetch("https://jobs.ashbyhq.com/ashby/abc")

    assert "Pilot Job" in md


def test_ashby_url_without_ldjson_routes_to_board_api(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))
    fetcher = WebpageFetcher(
        [JsonLdSource(), AshbyBoardSource(), StaticSource()],
        page_get=lambda url: "<html><body>ashby js shell</body></html>")

    md = fetcher.fetch("https://jobs.ashbyhq.com/ashby/abc-1")

    assert "Board Job" in md


def test_failed_page_get_still_routes_to_ashby_board_api(monkeypatch):
    """A blocked page GET doesn't kill the URL-decidable board-api source."""
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))
    def fail(url):
        raise FetchBlocked(403, "forbidden", url)
    fetcher = WebpageFetcher(
        [JsonLdSource(), AshbyBoardSource(), StaticSource()], page_get=fail)

    md = fetcher.fetch("https://jobs.ashbyhq.com/ashby/abc-1")

    assert "Board Job" in md


def test_failed_page_get_non_ashby_raises_page_status():
    def fail(url):
        raise FetchBlocked(403, "forbidden", url)
    fetcher = WebpageFetcher(
        [JsonLdSource(), AshbyBoardSource(), StaticSource()], page_get=fail)

    with pytest.raises(FetchBlocked) as exc_info:
        fetcher.fetch("https://example.com/job")

    assert exc_info.value.status == 403


def test_extract_failure_falls_through_to_next_source():
    failing = StubSource(supports=True, exc=FetchBlocked(503, "api down", "u"))
    backup = StubSource(supports=True, result=(None, "<p>page</p>"))
    fetcher = WebpageFetcher([failing, backup], page_get=lambda url: "<html/>")

    md = fetcher.fetch("https://x/job")

    assert "page" in md
    assert len(backup.extract_calls) == 1


def test_extract_failure_without_fallback_raises_extract_error():
    fetcher = WebpageFetcher(
        [StubSource(supports=True, exc=FetchBlocked(503, "api down", "u"))],
        page_get=lambda url: "<html/>")

    with pytest.raises(FetchBlocked) as exc_info:
        fetcher.fetch("https://x/job")

    assert exc_info.value.status == 503


def test_no_matching_source_raises_without_extracting():
    src = StubSource(supports=False)
    fetcher = WebpageFetcher([src], page_get=lambda url: "<html/>")

    with pytest.raises(FetchBlocked):
        fetcher.fetch("https://example.com/job")

    assert src.extract_calls == []


def test_main_prints_markdown_and_returns_it(monkeypatch, capsys):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=LD_PAGE.encode()))

    md = main(["https://jobs.ashbyhq.com/ashby/abc"])

    assert isinstance(md, str)
    assert "Pilot Job" in md
    assert "Pilot Job" in capsys.readouterr().out


def test_main_returns_none_on_http_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=403, text="denied"))

    rc = main(["https://example.com/careers/123"])

    assert rc is None
    assert "403" in capsys.readouterr().err


def test_main_returns_none_on_connection_error(monkeypatch, capsys):
    def boom(url, **kw):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(requests, "get", boom)

    rc = main(["https://example.com/job"])

    assert rc is None
    assert "error:" in capsys.readouterr().err
