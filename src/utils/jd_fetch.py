"""jd_fetch.py — fetch a job description as markdown on stdout. Browserless.

The posting page is fetched once; the first source whose supports() matches
the (url, body) pair extracts (title, html), rendered by render_markdown.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from typing import Protocol

import requests
from markdownify import markdownify as to_markdown

UA = {"User-Agent": "resume-updater/1.0"}
TIMEOUT = 30


class FetchBlocked(Exception):
    """A source cannot serve this URL; carries the HTTP status."""

    def __init__(self, status: int, reason: str, url: str):
        super().__init__(f"{status} {reason}: {url}")
        self.status, self.reason, self.url = status, reason, url


class PageSource(Protocol):
    """Decides from (url, body) whether it can serve, then extracts JD html.

    body is None when the posting page itself could not be fetched; only
    URL-decidable sources — AshbyBoardSource, GreenhouseSource — can still
    answer then, since they match on the URL alone and hit their own APIs.
    """

    def supports(self, url: str, body: str | None) -> bool: ...
    def extract(self, url: str, body: str | None) -> tuple[str | None, str]: ...


def _get(url: str) -> requests.Response:
    try:
        return requests.get(url, headers=UA, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise FetchBlocked(0, f"request failed: {type(exc).__name__}", url) from exc


def _text(resp: requests.Response) -> str:
    """Body decoded as UTF-8 when valid — unlabelled text is usually UTF-8,
    not the ISO-8859-1 requests assumes without a charset header."""
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return resp.text


def get_page(url: str) -> str:
    """The one GET of the posting page, shared by every source."""
    resp = _get(url)
    if resp.status_code != 200:
        raise FetchBlocked(resp.status_code, "non-200", url)
    return _text(resp)


_LD_SCRIPT = re.compile(
    r'<script\b[^>]*?\stype\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I)


def _job_posting(body: str) -> dict | None:
    for raw in _LD_SCRIPT.findall(body):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        types = data.get("@type")
        if not isinstance(types, list):
            types = [types]
        if "JobPosting" in types and "description" in data:
            return data
    return None


class JsonLdSource:
    """Static posting page embedding a ld+json JobPosting block."""

    def supports(self, url: str, body: str | None) -> bool:
        return body is not None and _job_posting(body) is not None

    def extract(self, url: str, body: str | None) -> tuple[str | None, str]:
        data = _job_posting(body or "")
        if data is None:
            raise FetchBlocked(200, "no ld+json JobPosting", url)
        return data.get("title"), data["description"]


_ASHBY_URL = re.compile(r"jobs\.ashbyhq\.com/([^/<>\s?#]+)/([^/<>\s?#]+)", re.I)


class AshbyBoardSource:
    """Ashby posting: public posting-api board list, match the job id.

    URL-decidable — can still answer when the page GET itself failed.
    """

    def supports(self, url: str, body: str | None) -> bool:
        return _ASHBY_URL.search(url) is not None

    def extract(self, url: str, body: str | None) -> tuple[str | None, str]:
        org, job_id = _ASHBY_URL.search(url).groups()
        resp = _get(f"https://api.ashbyhq.com/posting-api/job-board/{org}")
        if resp.status_code != 200:
            raise FetchBlocked(resp.status_code, "board api non-200", url)
        try:
            payload = json.loads(resp.content)
        except ValueError:
            raise FetchBlocked(resp.status_code, "board api returned non-JSON", url) from None
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        for job in jobs:
            if job.get("id") == job_id and "descriptionHtml" in job:
                return job.get("title"), job["descriptionHtml"]
        raise FetchBlocked(resp.status_code, "job id not in board list", url)


_GH_URL = re.compile(
    r"(?:job-boards|boards)\.greenhouse\.io/([^/<>\s?#]+)/jobs/([^/<>\s?#]+)", re.I)


class GreenhouseSource:
    """Greenhouse posting: public boards-api job JSON (title + content).

    URL-decidable like AshbyBoardSource — job-boards pages have no ld+json.
    """

    def supports(self, url: str, body: str | None) -> bool:
        return _GH_URL.search(url) is not None

    def extract(self, url: str, body: str | None) -> tuple[str | None, str]:
        board, job_id = _GH_URL.search(url).groups()
        resp = _get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
        if resp.status_code != 200:
            raise FetchBlocked(resp.status_code, "boards-api non-200", url)
        try:
            data = json.loads(resp.content)
        except ValueError:
            raise FetchBlocked(resp.status_code, "boards-api returned non-JSON", url) from None
        if not isinstance(data, dict) or "content" not in data:
            raise FetchBlocked(resp.status_code, "boards-api missing job content", url)
        return data.get("title"), data["content"]


class StaticSource:
    """Catch-all: serve the fetched SSR page body as-is (never Ashby shells).

    Ashby pages are JS shells (the JD lives only in meta/ld blocks, which
    JsonLdSource/AshbyBoardSource already cover). Greenhouse stays eligible:
    its pages are real SSR, a degraded fallback when boards-api fails.
    """

    def supports(self, url: str, body: str | None) -> bool:
        return body is not None and "jobs.ashbyhq.com" not in url.lower()

    def extract(self, url: str, body: str | None) -> tuple[str | None, str]:
        return None, body or ""


_TAG = re.compile(r"</?[a-zA-Z]")


def render_markdown(title: str | None, html: str) -> str:
    """The single md step every source feeds: title header + html → markdown."""
    if "&lt;" in html and not _TAG.search(html):
        html = unescape(html)
    md = to_markdown(html)
    return f"# {title}\n\n{md}" if title else md


class WebpageFetcher:
    """Fetches the page once; routes to the first source that supports it."""

    def __init__(self, sources: list[PageSource], page_get=get_page):
        self.sources = list(sources)
        self.page_get = page_get

    def fetch(self, url: str) -> str:
        body, last_err = None, None
        try:
            body = self.page_get(url)
        except FetchBlocked as exc:
            last_err = exc
        for src in self.sources:
            if not src.supports(url, body):
                continue
            try:
                title, html = src.extract(url, body)
                return render_markdown(title, html)
            except FetchBlocked as exc:
                last_err = exc
        raise last_err or FetchBlocked(200, "no source matched this page", url)


def main(argv: list[str] | None = None) -> int:
    """CLI: jd_fetch.py <url> — markdown to stdout. 0 on success, 1 on failure."""
    parser = argparse.ArgumentParser(description="Fetch a job description as markdown.")
    parser.add_argument("url")
    args = parser.parse_args(argv)
    # Selection order: embedded ld+json → URL-decidable board APIs → SSR body.
    fetcher = WebpageFetcher(
        [JsonLdSource(), AshbyBoardSource(), GreenhouseSource(), StaticSource()])
    try:
        print(fetcher.fetch(args.url))
    except FetchBlocked as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
