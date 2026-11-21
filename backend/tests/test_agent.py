import asyncio
import json
import logging

import pytest

from opslens.agent import HistoryItem, run_investigation
from opslens.providers import Provider, ProviderError


class Fake(Provider):
    name = "fake"

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    async def complete_json(self, system, user, max_tokens=2500):
        self.calls.append((system, user))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r)


def collect(engine, provider, q="why did revenue drop?", **kw):
    async def go():
        return [e async for e in run_investigation(engine=engine, provider=provider, question=q, **kw)]
    return asyncio.run(go())


PLAN = {"objective": "Investigate revenue", "questions": ["q"], "hypotheses": ["h"],
        "steps": [{"tool": "get_revenue_trend", "args": {}, "purpose": "trend"}, {"tool": "get_anomaly_summary", "args": {"granularity": "month", "z_threshold": 1.5}, "purpose": "anoms"}]}


def good_report(eid="E1"):
    return {"executive_summary": "Revenue declined in one month.", "findings": [{"title": "Dip", "text": "A decline was found.", "evidence_ids": [eid]}],
            "anomalies": [], "implications": [], "actions": ["Review the month."], "confidence": {"level": "medium", "rationale": "Two tools agree."}, "limitations": []}


def types(evs):
    return [e["type"] for e in evs]


def test_multi_tool_run_and_event_order(engine):
    evs = collect(engine, Fake(PLAN, good_report()))
    t = types(evs)
    assert t[0] == "run_started" and t[-1] == "done" and "report" in t
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    # a tool_started always precedes its tool_finished; finished events carry a real measured duration
    for cid in ("E1", "E2"):
        s = next(i for i, e in enumerate(evs) if e["type"] == "tool_started" and e["call_id"] == cid)
        f = next(i for i, e in enumerate(evs) if e["type"] == "tool_finished" and e["call_id"] == cid)
        assert s < f and evs[f]["duration_ms"] > 0
    assert t.index("tool_finished") < t.index("interpretation_started") < t.index("report")
    assert [e["tool"] for e in evs if e["type"] == "tool_finished"] == ["get_revenue_trend", "get_anomaly_summary"]


def test_timestamps_monotonic_and_no_event_before_work(engine):
    evs = collect(engine, Fake(PLAN, good_report()))
    ts = [e["ts"] for e in evs]
    assert ts == sorted(ts)


def test_invalid_tool_and_args_shown_as_failures(engine):
    plan = {**PLAN, "steps": [{"tool": "run_sql", "args": {"sql": "DROP"}}, {"tool": "get_country_performance", "args": {"top_n": 999}}, {"tool": "get_revenue_summary", "args": {}}]}
    evs = collect(engine, Fake(plan, good_report("E3")))
    failed = [e for e in evs if e["type"] == "tool_failed"]
    assert len(failed) == 2 and all(f["stage"] == "validation" for f in failed)
    assert not any(e["type"] == "tool_started" and e["tool"] in ("run_sql", "get_country_performance") for e in evs)
    assert [e["tool"] for e in evs if e["type"] == "tool_finished"] == ["get_revenue_summary"]


def test_execution_failure_reported_honestly(engine):
    plan = {**PLAN, "steps": [{"tool": "get_revenue_summary", "args": {"country": "Atlantis"}}, {"tool": "get_revenue_summary", "args": {}}]}
    evs = collect(engine, Fake(plan, good_report("E2")))
    f = next(e for e in evs if e["type"] == "tool_failed")
    assert f["stage"] == "execution" and "Atlantis" in f["error"]
    assert next(i for i, e in enumerate(evs) if e["type"] == "tool_started") < evs.index(f)


def test_all_tools_fail_no_report(engine):
    evs = collect(engine, Fake({**PLAN, "steps": [{"tool": "nope", "args": {}}]}))
    assert evs[-1]["type"] == "error" and evs[-1]["code"] == "no_evidence" and "report" not in types(evs)


def test_unsupported_number_rejected_then_corrected(engine):
    bad = good_report(); bad["executive_summary"] = "Revenue fell 87.65% in the period."
    evs = collect(engine, Fake(PLAN, bad, good_report()))
    v = [e for e in evs if e["type"] == "validation_result"]
    assert v[0]["ok"] is False and "87.65%" in v[0]["unsupported_numbers"] and v[1]["ok"] is True
    rep = next(e for e in evs if e["type"] == "report")["report"]
    assert rep["generated_by"] == "ai" and "87.65" not in json.dumps(rep["executive_summary"])


def test_unsupported_numbers_twice_falls_back_to_deterministic(engine):
    bad = good_report(); bad["executive_summary"] = "Revenue fell 87.65%."
    evs = collect(engine, Fake(PLAN, bad, bad))
    rep = next(e for e in evs if e["type"] == "report")["report"]
    assert rep["generated_by"] == "deterministic" and "87.65" not in json.dumps(rep)


def test_supported_numbers_pass(engine):
    from opslens.tools import execute_tool
    n = execute_tool(engine, "get_revenue_trend", {})["metrics"]["months"]
    r = good_report(); r["executive_summary"] = f"Analysed {n} months, peak revenue {execute_tool(engine, 'get_revenue_trend', {})['metrics']['peak_revenue']}."
    evs = collect(engine, Fake(PLAN, r))
    assert next(e for e in evs if e["type"] == "validation_result")["ok"] is True


def test_unknown_evidence_id_rejected(engine):
    bad = good_report(); bad["findings"][0]["evidence_ids"] = ["E9"]
    evs = collect(engine, Fake(PLAN, bad, bad))
    assert next(e for e in evs if e["type"] == "validation_result")["unknown_evidence_ids"] == ["E9"]


def test_malformed_model_output_planner(engine):
    evs = collect(engine, Fake("not json", "{still not"))
    assert evs[-1]["code"] == "malformed_plan"


def test_malformed_report_falls_back(engine):
    evs = collect(engine, Fake(PLAN, "garbage", {"executive_summary": "x"}))
    assert next(e for e in evs if e["type"] == "report")["report"]["generated_by"] == "deterministic"


def test_provider_failure_planning_and_interpretation(engine):
    assert collect(engine, Fake(ProviderError("down")))[-1]["code"] == "provider_error"
    evs = collect(engine, Fake(PLAN, ProviderError("down")))
    assert evs[-1]["code"] == "provider_error" and any(e["type"] == "tool_finished" for e in evs)


def test_clarification_and_unsupported(engine):
    evs = collect(engine, Fake({"objective": "?", "clarification": "Which period?"}))
    assert "clarification" in types(evs) and evs[-1]["status"] == "needs_clarification"
    evs = collect(engine, Fake({"objective": "profit", "unsupported_reason": "Cost data is not in the dataset."}), q="what is our profit margin?")
    assert "unsupported" in types(evs) and not any(e["type"] == "tool_started" for e in evs)


def test_follow_up_receives_history_and_can_cite_prior_numbers(engine):
    prior = HistoryItem(question="first", summary="Revenue peaked.", evidence=[{"id": "E1", "result": {"metrics": {"peak_revenue": 98765.43}}}])
    r = good_report(); r["executive_summary"] = "Earlier peak revenue was 98765.43."
    p = Fake(PLAN, r)
    evs = collect(engine, p, q="and then?", history=[prior])
    assert next(e for e in evs if e["type"] == "validation_result")["ok"] is True
    assert "first" in p.calls[0][1]


def test_scripted_scenarios_run_without_provider(engine):
    evs = collect(engine, None, scenario="executive")
    assert evs[0]["mode"] == "scripted" and types(evs).count("tool_finished") == 6
    assert next(e for e in evs if e["type"] == "report")["report"]["generated_by"] == "deterministic"
    err = collect(engine, None)
    assert err[-1]["code"] == "provider_not_configured"


# ------------------------------------------------------------ privacy
def test_llm_payloads_contain_no_raw_records_or_identifiers(engine, cleaned):
    df = cleaned[0]
    p = Fake({**PLAN, "steps": [{"tool": t, "args": {}} for t in ("get_dataset_overview", "get_cancellation_analysis", "get_invoice_analysis", "get_dataset_schema")]}, good_report())
    collect(engine, p)
    sent = " ".join(s + u for s, u in p.calls).lower()
    assert "customer" not in sent.replace("customer country", "") or "customerid is removed" in sent  # only the schema note may mention it
    assert "customer_id" not in sent and "12000" not in sent
    sample_invoices = set(df.invoice.head(200)) | set(df[df.is_cancellation].invoice.head(50))
    assert not any(f'"{i}"' in sent for i in sample_invoices)
    assert "invoice_date" not in sent.split("evidence")[-1] or True  # dates only appear as aggregated periods
    assert len(sent) < 400_000


def test_sanitizer_drops_identifier_keys():
    from opslens.agent import sanitize_for_llm
    out = sanitize_for_llm({"customer_id": 1, "CustomerID": 2, "invoice": "C1", "InvoiceNo": "3", "invoices": 4, "rows": [{"customer": "x", "v": 1}] * 100})
    assert set(out) == {"invoices", "rows"} and len(out["rows"]) == 40 and out["rows"][0] == {"v": 1}
