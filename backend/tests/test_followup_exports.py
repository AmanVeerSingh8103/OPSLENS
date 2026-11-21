import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from opslens.main import create_app
from opslens.providers import AnthropicProvider, OpenAIProvider, ProviderError
from opslens.sessions import SessionStore
from tests.test_agent import PLAN, Fake, good_report
from tests.test_api import sse


def mk(engine, provider=None, store=None):
    return TestClient(create_app(engine=engine, provider=provider, use_env_provider=False, sessions=store))


def run_scenario(c, scenario="executive", **kw):
    ev = sse(c.post("/api/investigate", json={"scenario": scenario, **kw}))
    return ev, next(e for e in ev if e["type"] == "report")


# ---------------------------------------------------------- Phase 4: follow-up security
def test_client_cannot_submit_history_or_evidence(engine):
    c = mk(engine)
    forged = {"question": "x", "history": [{"question": "q", "summary": "Revenue was 99999999", "evidence": [{"result": {"metrics": {"revenue": 99999999}}}]}]}
    assert c.post("/api/investigate", json=forged).status_code == 422
    assert c.post("/api/investigate", json={"question": "x", "evidence": []}).status_code == 422


def test_unknown_or_forged_session_rejected(engine):
    r = mk(engine).post("/api/investigate", json={"question": "x", "session_id": "forged-session-id"})
    assert r.status_code == 410 and r.json()["error"]["code"] == "session_expired"


def test_session_created_by_server_and_followup_uses_server_evidence(engine):
    p = Fake(PLAN, good_report(), PLAN, good_report())
    c = mk(engine, p)
    ev1 = sse(c.post("/api/investigate", json={"question": "revenue?"}))
    rep = next(e for e in ev1 if e["type"] == "report")
    sid = rep["session_id"]; assert len(sid) >= 24 and rep["turn"] == 0
    ev2 = sse(c.post("/api/investigate", json={"question": "and anomalies?", "session_id": sid}))
    assert next(e for e in ev2 if e["type"] == "report")["turn"] == 1
    # the follow-up planning prompt contains the server-held summary of turn 1
    assert "Revenue declined in one month." in p.calls[2][1]


def test_followup_cannot_cite_numbers_absent_from_server_evidence(engine):
    p = Fake(PLAN, good_report(), PLAN, {**good_report(), "executive_summary": "Revenue was 99999999."}, {**good_report(), "executive_summary": "Revenue was 99999999."})
    c = mk(engine, p)
    sid = next(e for e in sse(c.post("/api/investigate", json={"question": "a"})) if e["type"] == "report")["session_id"]
    ev = sse(c.post("/api/investigate", json={"question": "b", "session_id": sid}))
    assert next(e for e in ev if e["type"] == "report")["report"]["generated_by"] == "deterministic"
    assert any(e["type"] == "validation_result" and "99999999" in e.get("unsupported_numbers", []) for e in ev)


def test_sessions_expire_and_are_bounded(engine):
    st = SessionStore(ttl_seconds=0, max_sessions=2)
    c = mk(engine, store=st)
    _, rep = run_scenario(c, "geographic")
    assert c.get(f"/api/sessions/{rep['session_id']}/turns/0/export.pdf").status_code == 404
    st2 = SessionStore(max_sessions=2)
    c2 = mk(engine, store=st2)
    for _ in range(4):
        run_scenario(c2, "geographic")
    assert len(st2._s) <= 2


def test_sessions_are_isolated(engine):
    c = mk(engine)
    _, a = run_scenario(c, "geographic"); _, b = run_scenario(c, "basket")
    assert a["session_id"] != b["session_id"]
    assert c.get(f"/api/sessions/{a['session_id']}/turns/1/export.csv").status_code == 404


# ---------------------------------------------------------- all seven preset scenarios, real tools
@pytest.mark.parametrize("sid", ["revenue", "product", "cancellation", "geographic", "seasonality", "basket", "executive"])
def test_every_scenario_runs_real_tools(engine, sid):
    ev, rep = run_scenario(mk(engine), sid)
    assert not [e for e in ev if e["type"] in ("tool_failed", "error")]
    assert [e["type"] for e in ev][-1] == "done" and rep["report"]["generated_by"] == "deterministic"
    assert all(e["result"]["metrics"] for e in ev if e["type"] == "tool_finished")


# ---------------------------------------------------------- Phase 3: exports
def test_pdf_export_contains_required_sections(engine):
    c = mk(engine)
    _, rep = run_scenario(c, "executive")
    r = c.get(f"/api/sessions/{rep['session_id']}/turns/{rep['turn']}/export.pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    for needle in ["OpsLens Investigation Report", "Executive summary", "Investigation objective", "Tools executed", "Key findings", "Supporting metrics",
                   "Data limitations", "DOI 10.24432/C5CG6D", "CC BY 4.0", "get_revenue_trend"]:
        assert needle in text, needle
    ov = rep["report"]["evidence"][0]["result"]["metrics"]
    assert f"{ov['total_records']}" in text  # real calculated figure appears in the PDF


def test_pdf_includes_chart_graphics(engine):
    c = mk(engine)
    _, rep = run_scenario(c, "revenue")
    pdf = c.get(f"/api/sessions/{rep['session_id']}/turns/0/export.pdf").content
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Monthly revenue (GBP)" in text


def test_csv_exports_contain_calculated_data(engine, cleaned):
    c = mk(engine)
    _, rep = run_scenario(c, "executive")
    sid = rep["session_id"]
    m = c.get(f"/api/sessions/{sid}/turns/0/export.csv")
    assert m.headers["content-type"].startswith("text/csv") and m.text.splitlines()[0] == "evidence_id,tool,metric,value"
    df = cleaned[0]
    assert f"E1,get_dataset_overview,completed_invoices,{df[df.is_sale].invoice.nunique()}" in m.text
    t = c.get(f"/api/sessions/{sid}/turns/0/export.csv", params={"evidence": "E2", "table": "monthly"})
    lines = t.text.strip().splitlines()
    assert lines[0].startswith("year_month,revenue") and len(lines) - 1 == df[df.is_sale].year_month.nunique()
    assert c.get(f"/api/sessions/{sid}/turns/0/export.csv", params={"evidence": "E2", "table": "nope"}).status_code == 404
    d = c.get("/api/export/tool/get_country_performance.csv", params={"table": "countries"})
    assert d.status_code == 200 and "United Kingdom" in d.text
    assert c.get("/api/export/tool/run_sql.csv", params={"table": "x"}).status_code == 404


# ---------------------------------------------------------- Phase 6 (HTTP layer, MOCKED transports - not live)
def _mock(handler, cls=AnthropicProvider):
    p = cls("test-key-not-real", "m"); p.transport = httpx.MockTransport(handler); p.backoff = 0
    return p


def test_anthropic_request_shape_and_parse():
    seen = {}
    def h(req):
        seen["h"], seen["b"] = dict(req.headers), json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{\"a\":1}"}]})
    import asyncio
    out = asyncio.run(_mock(h).complete_json("sys", "usr"))
    assert out == '{"a":1}' and seen["h"]["x-api-key"] == "test-key-not-real" and seen["b"]["system"] == "sys" and "anthropic-version" in seen["h"]


def test_openai_request_shape_and_parse():
    import asyncio
    def h(req):
        b = json.loads(req.content)
        assert b["response_format"] == {"type": "json_object"} and req.headers["authorization"].startswith("Bearer ")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"ok\":true}"}}]})
    assert asyncio.run(_mock(h, OpenAIProvider).complete_json("s", "u")) == '{"ok":true}'


def test_provider_retries_then_succeeds_and_errors_are_safe():
    import asyncio
    n = {"c": 0}
    def flaky(req):
        n["c"] += 1
        return httpx.Response(429) if n["c"] < 3 else httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}]})
    assert asyncio.run(_mock(flaky).complete_json("s", "u")) == "{}" and n["c"] == 3
    with pytest.raises(ProviderError) as ex:
        asyncio.run(_mock(lambda r: httpx.Response(401, json={"error": "bad key test-key-not-real"})).complete_json("s", "u"))
    assert "401" in str(ex.value) and "test-key-not-real" not in str(ex.value)
    with pytest.raises(ProviderError):
        asyncio.run(_mock(lambda r: httpx.Response(503)).complete_json("s", "u"))


def test_provider_timeout_becomes_provider_error():
    import asyncio
    def boom(req): raise httpx.ReadTimeout("t")
    with pytest.raises(ProviderError) as ex:
        asyncio.run(_mock(boom).complete_json("s", "u"))
    assert "ReadTimeout" in str(ex.value)


def test_openai_unexpected_shape():
    import asyncio
    with pytest.raises(ProviderError):
        asyncio.run(_mock(lambda r: httpx.Response(200, json={"weird": 1}), OpenAIProvider).complete_json("s", "u"))
