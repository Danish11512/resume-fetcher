"""TDD tests for utils/jd_fetch.py — plan: plans/jd-fetcher.md.

Every test is stubbed: zero network, zero browser (plan §4).
"""
import json
from types import SimpleNamespace

import pytest
import requests

from jd_fetch import (
    FetchBlocked, extract_ashby, extract_greenhouse, extract_jsonld,
    extract_static, fetch, get_page, main, render_markdown, supports_ashby,
    supports_greenhouse, supports_jsonld, supports_static,
)


def stub_source(supports=False, result=None, exc=None):
    """Inert source pair: preset supports flag, preset extract result/exc.

    Returns (supports_fn, extract_fn, extract_calls).
    """
    calls = []

    def sup(url, body):
        return supports

    def ext(url, body):
        calls.append((url, body))
        if exc is not None:
            raise exc
        return result

    return sup, ext, calls


def test_fetch_returns_markdown_with_title_header():
    sup, ext, calls = stub_source(
        supports=True, result=("Eng Manager - EU", "<p>Write <b>go</b> code.</p>"))

    md = fetch("https://example.com/job", sources=[(sup, ext)],
               page_get=lambda url: "<html/>")

    assert md.startswith("# Eng Manager - EU")
    assert "Write **go** code." in md
    assert calls == [("https://example.com/job", "<html/>")]


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
    url = "https://jobs.ashbyhq.com/ashby/abc"

    assert supports_jsonld(url, LD_PAGE)
    assert extract_jsonld(url, LD_PAGE) == ("Pilot Job", "<p>Do <b>things</b>.</p>")


def test_jsonld_source_rejects_page_without_jobposting():
    body = "<html><body>shell</body></html>"

    assert not supports_jsonld("https://x/job", body)
    with pytest.raises(FetchBlocked) as exc_info:
        extract_jsonld("https://x/job", body)
    assert exc_info.value.status == 200


def test_jsonld_source_requires_body():
    assert not supports_jsonld("https://x/job", None)


def test_jsonld_source_handles_type_list_array_toplevel_and_extra_attrs():
    body = (
        '<script type="application/ld+json">[{"@type":"BreadcrumbList"}]</script>'
        '<script data-extra="1" type="application/ld+json">'
        '{"@type":["JobPosting"],"title":"T","description":"<p>D</p>"}</script>'
    )

    assert supports_jsonld("https://x/job", body)
    assert extract_jsonld("https://x/job", body) == ("T", "<p>D</p>")


BOARD = {"jobs": [
    {"id": "abc-1", "title": "Board Job", "descriptionHtml": "<p>board desc</p>"},
    {"id": "def-2", "title": "Other Job", "descriptionHtml": "<p>other</p>"},
]}


def test_board_source_is_url_decidable_without_body():
    assert supports_ashby("https://jobs.ashbyhq.com/ashby/abc-1", None)
    assert not supports_ashby("https://example.com/careers/123", "<html/>")


def test_board_source_extract_matches_job_id(monkeypatch):
    seen = {}
    def fake_get(url, **kw):
        seen["url"] = url
        return SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode())
    monkeypatch.setattr(requests, "get", fake_get)

    title, html = extract_ashby("https://jobs.ashbyhq.com/ashby/abc-1", None)

    assert (title, html) == ("Board Job", "<p>board desc</p>")
    assert seen["url"] == "https://api.ashbyhq.com/posting-api/job-board/ashby"


def test_board_source_ignores_query_string_in_job_id(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))

    title, _ = extract_ashby(
        "https://jobs.ashbyhq.com/ashby/abc-1?utm_source=x", None)

    assert title == "Board Job"


def test_board_source_blocks_when_id_missing(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))

    with pytest.raises(FetchBlocked):
        extract_ashby(
            "https://jobs.ashbyhq.com/ashby/00000000-0000-0000-0000-000000000000", None)


GH_JOB = {"title": "Software Engineer, eve", "content": "<p>eve desc</p>"}


def test_greenhouse_source_is_url_decidable_without_body():
    assert supports_greenhouse("https://job-boards.greenhouse.io/vercel/jobs/6098390004", None)
    assert supports_greenhouse("https://boards.greenhouse.io/vercel/jobs/6098390004", None)
    assert not supports_greenhouse("https://example.com/careers/123", "<html/>")


def test_greenhouse_source_extract_returns_title_and_content(monkeypatch):
    seen = {}
    def fake_get(url, **kw):
        seen["url"] = url
        return SimpleNamespace(status_code=200, content=json.dumps(GH_JOB).encode())
    monkeypatch.setattr(requests, "get", fake_get)

    title, html = extract_greenhouse(
        "https://job-boards.greenhouse.io/vercel/jobs/6098390004", None)

    assert (title, html) == ("Software Engineer, eve", "<p>eve desc</p>")
    assert seen["url"] == "https://boards-api.greenhouse.io/v1/boards/vercel/jobs/6098390004"


def test_greenhouse_source_blocks_on_api_failure(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=404, content=b"not found"))

    with pytest.raises(FetchBlocked) as exc_info:
        extract_greenhouse("https://job-boards.greenhouse.io/x/jobs/1", None)

    assert exc_info.value.status == 404


def test_greenhouse_source_blocks_on_missing_content(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=b'{"title":"T"}'))

    with pytest.raises(FetchBlocked):
        extract_greenhouse("https://job-boards.greenhouse.io/x/jobs/1", None)


def test_get_page_decodes_unlabelled_utf8(monkeypatch):
    """No charset header → requests guesses ISO-8859-1; the bytes are really UTF-8."""
    resp = SimpleNamespace(
        status_code=200, content="Cisco’s".encode("utf-8"), text="Ciscoâs")
    monkeypatch.setattr(requests, "get", lambda url, **kw: resp)

    assert get_page("https://x/job") == "Cisco’s"


def test_static_source_serves_ssr_body_but_never_ashby_or_bodiless():
    assert supports_static("https://example.com/job", "<p>x</p>")
    assert extract_static("https://example.com/job", "<p>x</p>") == (None, "<p>x</p>")
    assert not supports_static("https://jobs.ashbyhq.com/ashby/abc", "<html/>")
    assert not supports_static("https://example.com/job", None)


def test_routing_prefers_jsonld_over_ashby_api(monkeypatch):
    """Ashby page WITH ld+json: jsonld wins, the board api is never called."""
    def boom(url, **kw):
        raise AssertionError(f"unexpected GET {url}")
    monkeypatch.setattr(requests, "get", boom)

    md = fetch("https://jobs.ashbyhq.com/ashby/abc", page_get=lambda url: LD_PAGE)

    assert "Pilot Job" in md


def test_ashby_url_without_ldjson_routes_to_board_api(monkeypatch):
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))

    md = fetch("https://jobs.ashbyhq.com/ashby/abc-1",
               page_get=lambda url: "<html><body>ashby js shell</body></html>")

    assert "Board Job" in md


def test_failed_page_get_still_routes_to_ashby_board_api(monkeypatch):
    """A blocked page GET doesn't kill the URL-decidable board-api source."""
    monkeypatch.setattr(
        requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, content=json.dumps(BOARD).encode()))
    def fail(url):
        raise FetchBlocked(403, "forbidden", url)

    md = fetch("https://jobs.ashbyhq.com/ashby/abc-1", page_get=fail)

    assert "Board Job" in md


def test_failed_page_get_non_ashby_raises_page_status():
    def fail(url):
        raise FetchBlocked(403, "forbidden", url)

    with pytest.raises(FetchBlocked) as exc_info:
        fetch("https://example.com/job", page_get=fail)

    assert exc_info.value.status == 403


def test_extract_failure_falls_through_to_next_source():
    f_sup, f_ext, _ = stub_source(supports=True, exc=FetchBlocked(503, "api down", "u"))
    b_sup, b_ext, b_calls = stub_source(supports=True, result=(None, "<p>page</p>"))

    md = fetch("https://x/job", sources=[(f_sup, f_ext), (b_sup, b_ext)],
               page_get=lambda url: "<html/>")

    assert "page" in md
    assert len(b_calls) == 1


def test_extract_failure_without_fallback_raises_extract_error():
    sup, ext, _ = stub_source(supports=True, exc=FetchBlocked(503, "api down", "u"))

    with pytest.raises(FetchBlocked) as exc_info:
        fetch("https://x/job", sources=[(sup, ext)], page_get=lambda url: "<html/>")

    assert exc_info.value.status == 503


def test_no_matching_source_raises_without_extracting():
    sup, ext, calls = stub_source(supports=False)

    with pytest.raises(FetchBlocked):
        fetch("https://example.com/job", sources=[(sup, ext)],
              page_get=lambda url: "<html/>")

    assert calls == []


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
