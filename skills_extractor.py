"""skills_extractor.py — classify JD candidate terms as skills via Jev.

JD markdown arrives on stdin (piped from jd_fetch.py) or as a file arg.
Candidate terms are generated locally; one Jev Choice question per candidate
fans out over OpenRouter's System One surface; the classification JSON goes
to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Protocol

import requests

MODEL = "typesafe/jev-1.13"
MAX_STATE_CHARS = 60_000
MAX_CANDIDATES = 150
TIMEOUT = 60


class TypeSafeError(Exception):
    """The System One call failed; carries the HTTP status."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"{status} {detail}")
        self.status, self.detail = status, detail


class JevClient(Protocol):
    """The one transport method SkillExtractor needs."""

    def ask(self, state: str, questions: dict[str, dict]) -> dict: ...


class HttpJevClient:
    """POSTs one fan-out decision to OpenRouter's System One endpoint."""

    def __init__(self, api_key: str, base: str = "https://openrouter.ai/api",
                 model: str = MODEL):
        self.api_key, self.base, self.model = api_key, base, model

    def ask(self, state: str, questions: dict[str, dict]) -> dict:
        try:
            resp = requests.post(
                f"{self.base}/v1/systemone",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"state": state, "model": self.model, "questions": questions},
                timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise TypeSafeError(0, f"request failed: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise TypeSafeError(resp.status_code, resp.text[:200])
        try:
            return resp.json()
        except ValueError as exc:
            raise TypeSafeError(
                200, f"response was not JSON: {type(exc).__name__}") from exc


_TOKEN = re.compile(r"\w[\w+#./-]*")
_STOPWORDS = frozenset("""
a an the and or of to in for on with at by from as is are was were be been
being have has had do does did will would could should may might must shall
can this that these those you your we our they their he she it its his her us
them i who what where when why how all any both each more most other some such
no not only same so than too very just but if then else about into over after
before between under again further once here there out up down off through
during while per etc via use using used
""".split())


def candidates(jd: str) -> list[str]:
    """1-2 word n-grams over tech-preserving tokens, deduped first-seen order."""
    tokens = [t.rstrip("./-") for t in _TOKEN.findall(jd)]
    terms, seen = [], set()
    for i, tok in enumerate(tokens):
        bigram = f"{tok} {tokens[i + 1]}" if i + 1 < len(tokens) else None
        for gram in (tok, bigram):
            if gram is None:
                continue
            words = gram.split()
            if any(len(w) < 2 or w.lower() in _STOPWORDS for w in words):
                continue
            key = gram.lower()
            if key not in seen:
                seen.add(key)
                terms.append(gram)
        if len(terms) >= MAX_CANDIDATES:
            break
    return terms[:MAX_CANDIDATES]


_CRITERIA = {
    "skill": "concrete tool/software/language/framework/platform/method "
             "the job asks the candidate to have or use",
    "not_skill": "anything else: duties, benefits, soft traits, "
                 "product or brand names, clients, degrees, years",
}


class SkillExtractor:
    """Fans one Choice question per candidate term out to Jev."""

    def __init__(self, client: JevClient, model: str = MODEL):
        self.client, self.model = client, model

    def extract(self, jd: str) -> dict:
        terms = candidates(jd)
        out = {"model": self.model, "candidates": []}
        if not terms:
            return out
        questions = {
            f"q{i}": {
                "type": "choice",
                "instructions": f"Is '{term}' a skill required or preferred in this job?",
                "criteria": _CRITERIA,
            }
            for i, term in enumerate(terms)
        }
        result = self.client.ask(jd[:MAX_STATE_CHARS], questions)
        answers = (result.get("answers") or result) if isinstance(result, dict) else {}
        for i, term in enumerate(terms):
            ans = answers.get(f"q{i}")
            ans = ans if isinstance(ans, dict) else {}
            out["candidates"].append({
                "term": term,
                "classification": ans.get("choice") or "unknown",
                "confidence": ans.get("confidence", 0.0),
                "probabilities": ans.get("probabilities", {}),
            })
        usage = result.get("usage") if isinstance(result, dict) else None
        if usage is not None:
            out["usage"] = usage
        return out


def load_api_key(env_path: Path | None = None) -> str | None:
    """OPENROUTER_API_KEY: env var wins, else a KEY=VALUE line in repo .env."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    path = env_path or Path(__file__).with_name(".env")
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if sep and name.strip() == "OPENROUTER_API_KEY":
            return value.strip() or None
    return None


def main(argv: list[str] | None = None,
         client: JevClient | None = None) -> dict | None:
    """Classify the piped/file JD: print JSON to stdout, return it; None on failure."""
    parser = argparse.ArgumentParser(
        description="Classify job-description terms as skills via Jev.")
    parser.add_argument(
        "file", nargs="?", help="JD markdown file; reads stdin when omitted.")
    args = parser.parse_args(argv)
    try:
        jd = Path(args.file).read_text() if args.file else sys.stdin.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    if not jd.strip():
        print("error: empty input (did jd_fetch fail?)", file=sys.stderr)
        return None
    if client is None:
        key = load_api_key()
        if not key:
            print("error: OPENROUTER_API_KEY not found in env or .env",
                  file=sys.stderr)
            return None
        client = HttpJevClient(key)
    try:
        out = SkillExtractor(client).extract(jd)
    except TypeSafeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    print(json.dumps(out, indent=2))
    if "usage" in out:
        print(f"usage: {json.dumps(out['usage'])}", file=sys.stderr)
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
