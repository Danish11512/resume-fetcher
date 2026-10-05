"""TDD tests for skills_extractor.py — plan: PLAN.md (Jev skill classifier).

Every test is stubbed: zero network, zero API key.
"""
import io
import json
import sys
from types import SimpleNamespace

import pytest

import skills_extractor
from skills_extractor import (
    HttpJevClient, SkillExtractor, TypeSafeError, candidates, load_api_key,
    main,
)


class StubClient:
    """Inert JevClient stub: preset answers (or exception), records ask()."""

    def __init__(self, answers=None, exc=None):
        self.answers, self.exc = answers or {}, exc
        self.ask_calls = []

    def ask(self, state, questions):
        self.ask_calls.append((state, questions))
        if self.exc is not None:
            raise self.exc
        return self.answers


ANSWERS = {
    "q0": {"choice": "skill", "confidence": 0.9,
           "probabilities": {"skill": 0.9, "not_skill": 0.1}},
    "q1": {"choice": "not_skill", "confidence": 0.7,
           "probabilities": {"skill": 0.3, "not_skill": 0.7}},
    "q2": {"choice": "skill", "confidence": 0.95,
           "probabilities": {"skill": 0.95, "not_skill": 0.05}},
}


def test_extract_maps_answers_to_terms():
    client = StubClient(ANSWERS)

    out = SkillExtractor(client).extract("python kubernetes")

    cands = out["candidates"]
    assert [c["term"] for c in cands] == ["python", "python kubernetes", "kubernetes"]
    for i, c in enumerate(cands):
        a = ANSWERS[f"q{i}"]
        assert c["classification"] == a["choice"]
        assert c["confidence"] == a["confidence"]
        assert c["probabilities"] == a["probabilities"]


def test_extract_sends_one_choice_question_per_candidate():
    client = StubClient(ANSWERS)

    SkillExtractor(client).extract("python kubernetes")

    state, questions = client.ask_calls[0]
    assert state == "python kubernetes"
    assert list(questions) == ["q0", "q1", "q2"]
    q0 = questions["q0"]
    assert q0["type"] == "choice"
    assert q0["instructions"] == "Is 'python' a skill required or preferred in this job?"
    assert set(q0["criteria"]) == {"skill", "not_skill"}


def test_tokenizer_keeps_tech_tokens():
    terms = candidates("We need C++ and C# plus node.js for CI/CD work.")

    assert "C++" in terms
    assert "C#" in terms
    assert "node.js" in terms
    assert "CI/CD" in terms


def test_candidates_dedupes_case_insensitively_keeping_first_casing():
    terms = candidates("Python python PYTHON")

    assert terms.count("Python") + terms.count("python") == 1
    assert terms[0] == "Python"


def test_extract_empty_jd_skips_api_call():
    client = StubClient()

    out = SkillExtractor(client).extract("")

    assert out["candidates"] == []
    assert client.ask_calls == []


def test_main_empty_stdin_errors(monkeypatch, capsys):
    constructed = []
    monkeypatch.setattr(
        skills_extractor, "HttpJevClient",
        lambda *a, **k: constructed.append((a, k)))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    rc = main([])

    assert rc is None
    assert "error: empty input (did jd_fetch fail?)" in capsys.readouterr().err
    assert constructed == []


def test_api_error_raises_and_main_reports(monkeypatch, capsys):
    client = StubClient(exc=TypeSafeError(401, "unauthorized"))

    with pytest.raises(TypeSafeError) as exc_info:
        SkillExtractor(client).extract("python kubernetes")
    assert exc_info.value.status == 401

    monkeypatch.setattr(sys, "stdin", io.StringIO("python kubernetes"))
    assert main([], client=client) is None
    assert "error:" in capsys.readouterr().err


def test_missing_answer_classified_unknown():
    client = StubClient({"q0": ANSWERS["q0"]})

    out = SkillExtractor(client).extract("python kubernetes")

    assert out["candidates"][0]["classification"] == "skill"
    assert out["candidates"][1]["classification"] == "unknown"
    assert out["candidates"][1]["confidence"] == 0.0


def test_state_and_question_caps_enforced():
    client = StubClient()
    jd = "".join(f"tok{i} " for i in range(30_000))
    assert len(jd) > 60_000

    SkillExtractor(client).extract(jd)

    state, questions = client.ask_calls[0]
    assert len(state) == 60_000
    assert len(questions) == 150


def test_env_key_loading(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nOPENROUTER_API_KEY=file-key\nOTHER=1\n")

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert load_api_key(env_file) == "file-key"

    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert load_api_key(env_file) == "env-key"

    monkeypatch.delenv("OPENROUTER_API_KEY")
    env_file.write_text("# nothing but comments\n\n")
    assert load_api_key(env_file) is None
    assert load_api_key(tmp_path / "missing-env") is None


def test_main_prints_parseable_json(monkeypatch, capsys):
    client = StubClient({"q0": ANSWERS["q0"]})
    monkeypatch.setattr(sys, "stdin", io.StringIO("python"))

    out = main([], client=client)

    printed = json.loads(capsys.readouterr().out)
    assert printed == out
    assert printed["candidates"][0]["term"] == "python"
    assert printed["candidates"][0]["classification"] == "skill"


def test_main_reads_file_arg(tmp_path):
    jd_file = tmp_path / "jd.md"
    jd_file.write_text("python")
    client = StubClient({"q0": ANSWERS["q0"]})

    out = main([str(jd_file)], client=client)

    assert out["candidates"][0]["term"] == "python"


def test_main_missing_file_reports_error(capsys):
    client = StubClient({})

    rc = main(["/nonexistent/path/jd.md"], client=client)

    assert rc is None
    assert "error:" in capsys.readouterr().err


def test_extract_passes_usage_through_from_envelope():
    client = StubClient({"answers": ANSWERS, "usage": {"input_tokens": 5}})

    out = SkillExtractor(client).extract("python")

    assert out["usage"] == {"input_tokens": 5}
    assert out["candidates"][0]["classification"] == "skill"


def test_ask_returns_full_envelope(monkeypatch):
    body = {"answers": {"q0": {"choice": "skill", "confidence": 1.0}},
            "usage": {"input_tokens": 9}}
    resp = SimpleNamespace(status_code=200, text="ok", json=lambda: body)
    monkeypatch.setattr(skills_extractor.requests, "post", lambda *a, **k: resp)

    out = HttpJevClient("k").ask("state", {})

    assert out == body


def test_ask_wraps_non_json_200_as_typesafe_error(monkeypatch):
    def bad_json():
        raise ValueError("Expecting value")
    resp = SimpleNamespace(status_code=200, text="<html>oops</html>", json=bad_json)
    monkeypatch.setattr(skills_extractor.requests, "post", lambda *a, **k: resp)

    with pytest.raises(TypeSafeError) as exc_info:
        HttpJevClient("k").ask("state", {})

    assert exc_info.value.status == 200
