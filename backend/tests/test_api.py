import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opslens.engine import DatasetNotReady
from opslens.main import create_app
from tests.test_agent import PLAN, Fake, good_report


def sse(resp):
    return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]


def client(engine, provider=None):
    return TestClient(create_app(engine=engine, provider=provider, use_env_provider=False))


def test_status_without_key(engine):
    j = client(engine).get("/api/status").json()
    assert j["dataset_ready"] and j["ai_configured"] is False and "CC BY 4.0" in j["license"]
    assert "sent to the configured AI provider" in j["privacy_notice"]


def test_dataset_missing_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSLENS_DATA_DIR", str(tmp_path))
    c = TestClient(create_app(use_env_provider=False))
    assert c.get("/api/status").json()["dataset_ready"] is False
    r = c.get("/api/explorer/preview")
    assert r.status_code == 503 and r.json()["error"]["code"] == "dataset_not_ready" and "opslens.ingest" in r.json()["error"]["message"]


def test_investigate_without_key_free_text_is_honest_error(engine):
    ev = sse(client(engine).post("/api/investigate", json={"question": "why did sales drop?"}))
    assert ev[-1]["type"] == "error" and ev[-1]["code"] == "provider_not_configured"


def test_investigate_scenario_streams_without_key(engine):
    r = client(engine).post("/api/investigate", json={"scenario": "geographic"})
    assert r.headers["content-type"].startswith("text/event-stream")
    assert [e["type"] for e in sse(r)][-1] == "done"


def test_investigate_with_fake_provider(engine):
    ev = sse(client(engine, Fake(PLAN, good_report())).post("/api/investigate", json={"question": "revenue?"}))
    assert any(e["type"] == "report" for e in ev)


def test_validation_and_unknown_tool(engine):
    c = client(engine)
    assert c.post("/api/investigate", json={"question": ""}).status_code == 422
    assert c.post("/api/investigate", json={"question": "x" * 5000}).status_code == 422
    assert c.post("/api/tools/run_sql", json={"sql": "select 1"}).status_code == 404
    r = c.post("/api/tools/get_revenue_summary", json={"country": "x'; DROP"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_tool_call"
    assert c.post("/api/tools/get_dataset_overview", json={}).json()["result"]["metrics"]["total_records"] > 0


def test_preview_excludes_identifiers_and_paginates(engine):
    j = client(engine).get("/api/explorer/preview?page=2&page_size=10").json()
    assert len(j["rows"]) == 10 and not ({"invoice", "customer_id"} & set(j["rows"][0]))
    assert client(engine).get("/api/explorer/preview?page_size=5000").status_code == 422


def test_rate_limit(engine, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    c = client(engine)
    codes = [c.post("/api/tools/get_dataset_overview", json={}).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]


def test_questions_and_keys_never_logged(engine, caplog, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET123")
    caplog.set_level(logging.DEBUG)
    secret_q = "CONFIDENTIAL-QUESTION-ABC revenue?"
    client(engine, Fake(PLAN, good_report())).post("/api/investigate", json={"question": secret_q})
    assert "CONFIDENTIAL-QUESTION-ABC" not in caplog.text and "SECRET123" not in caplog.text


def test_no_secret_in_frontend_env_and_source():
    root = Path(__file__).resolve().parents[2]
    ex = (root / ".env.example")
    if ex.exists():
        assert "NEXT_PUBLIC_" not in "".join(l for l in ex.read_text().splitlines() if "KEY" in l)
    src = " ".join(p.read_text() for p in (root / "backend/opslens").glob("*.py"))
    assert "sk-ant-" not in src and "sk-proj-" not in src
