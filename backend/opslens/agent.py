"""Agent loop. Every yielded event is emitted at the moment the corresponding backend action happens."""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncIterator, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .engine import Engine
from .numcheck import collect_numbers, find_unsupported
from .providers import Provider, ProviderError
from .tools import ToolError, tool_specs, validate_call

DATA_LIMITATIONS = [
    "Historical data (Dec 2009 - Dec 2011) from one UK online retailer; not live.",
    "Revenue is Quantity x UnitPrice on completed sale lines. It is not profit; costs and margins are unavailable.",
    "No marketing spend, staffing, stock-level or customer-level data is exposed, so ROI, productivity and inventory questions cannot be answered.",
    "Findings show association, not causation; explanations are hypotheses to test.",
]

SCENARIOS = {
    "revenue": ("Investigate the revenue trend and identify periods of significant decline.",
                [("get_revenue_trend", {}), ("get_anomaly_summary", {"granularity": "month", "z_threshold": 1.5}), ("get_seasonality_analysis", {})]),
    "product": ("Which products contribute most to revenue, and which products show declining performance?",
                [("get_product_performance", {"top_n": 10}), ("get_product_concentration", {}), ("get_top_bottom_performers", {"dimension": "product", "n": 5})]),
    "cancellation": ("Analyse cancellations and identify products and periods associated with the highest cancellation activity.",
                     [("get_cancellation_analysis", {"top_n": 10}), ("get_revenue_trend", {})]),
    "geographic": ("Which countries contribute most to sales, and how does performance differ across markets?",
                   [("get_country_performance", {"top_n": 10}), ("get_top_bottom_performers", {"dimension": "country", "n": 5})]),
    "seasonality": ("Identify seasonal sales patterns and unusual transaction activity.",
                    [("get_seasonality_analysis", {}), ("get_anomaly_summary", {"granularity": "day", "z_threshold": 3})]),
    "basket": ("Investigate average invoice value, quantities and product purchasing patterns.",
               [("get_average_invoice_value", {}), ("get_invoice_analysis", {}), ("get_quantity_analysis", {"top_n": 10}), ("get_product_concentration", {})]),
    "executive": ("Prepare an executive business performance report using the available dataset.",
                  [("get_dataset_overview", {}), ("get_revenue_trend", {}), ("get_country_performance", {"top_n": 5}), ("get_product_performance", {"top_n": 5}),
                   ("get_cancellation_analysis", {"top_n": 5}), ("get_data_quality_report", {})]),
}


# ---------------------------------------------------------------- schemas
class PlanStep(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    purpose: str = Field("", max_length=300)


class Plan(BaseModel):
    objective: str = Field(max_length=500)
    questions: list[str] = Field(default_factory=list, max_length=8)
    hypotheses: list[str] = Field(default_factory=list, max_length=8)
    steps: list[PlanStep] = Field(default_factory=list, max_length=8)
    clarification: Optional[str] = None
    unsupported_reason: Optional[str] = None


class Finding(BaseModel):
    title: str = Field(max_length=200)
    text: str = Field(max_length=1500)
    evidence_ids: list[str] = Field(min_length=1)


class Confidence(BaseModel):
    level: Literal["low", "medium", "high"]
    rationale: str = Field(max_length=600)


class Report(BaseModel):
    executive_summary: str = Field(max_length=2000)
    findings: list[Finding] = Field(min_length=1, max_length=8)
    anomalies: list[str] = Field(default_factory=list, max_length=10)
    implications: list[str] = Field(default_factory=list, max_length=8)
    actions: list[str] = Field(default_factory=list, max_length=8)
    confidence: Confidence
    limitations: list[str] = Field(default_factory=list, max_length=8)


class HistoryItem(BaseModel):
    question: str = Field(max_length=600)
    summary: str = Field(max_length=2500)
    evidence: list[dict] = Field(default_factory=list, max_length=20)


def report_texts(r: Report) -> list[str]:
    t = [r.executive_summary, r.confidence.rationale, *r.anomalies, *r.implications, *r.actions, *r.limitations]
    for f in r.findings:
        t += [f.title, f.text]
    return t


# ---------------------------------------------------------------- helpers
_FORBIDDEN = re.compile(r"customer|^invoice(_no)?$|^invoiceno$", re.I)


def sanitize_for_llm(obj: Any, depth: int = 0) -> Any:
    """Rule 3: defence in depth. Drops identifier-like keys and caps list sizes."""
    if isinstance(obj, dict):
        return {k: sanitize_for_llm(v, depth + 1) for k, v in obj.items() if not _FORBIDDEN.search(str(k))}
    if isinstance(obj, list):
        return [sanitize_for_llm(v, depth + 1) for v in obj[:40]]
    return obj


def extract_json(text: str) -> dict:
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object in model output")
    d = json.loads(text[i:j + 1])
    if not isinstance(d, dict):
        raise ValueError("model output is not a JSON object")
    return d


def deterministic_report(evs: list[dict], note: str) -> dict:
    findings = []
    for ev in evs:
        ms = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in list(ev["result"]["metrics"].items())[:10] if v is not None)
        findings.append({"title": ev["tool"].replace("get_", "").replace("_", " ").title(), "text": ms or "No metrics returned.", "evidence_ids": [ev["id"]]})
    return {"executive_summary": note, "findings": findings, "anomalies": [], "implications": [], "actions": [],
            "confidence": {"level": "medium", "rationale": "Figures are direct outputs of deterministic tools; no model interpretation was applied."},
            "limitations": [], "generated_by": "deterministic"}


PLAN_SYSTEM = """You are the planning module of OpsLens, a business-intelligence investigation agent for the UCI Online Retail II dataset (UK online retailer, 2009-2011).
You can ONLY use the registered analytical tools below. You cannot write SQL or code. You never calculate numbers yourself.
Return ONE JSON object and nothing else:
{"objective": str, "questions": [str], "hypotheses": [str], "steps": [{"tool": str, "args": {}, "purpose": str}], "clarification": str|null, "unsupported_reason": str|null}
Rules: max 8 steps, only listed tools, arguments must match the schemas. If the question is ambiguous, set "clarification" and no steps.
If the dataset cannot answer it (profit, marketing ROI, staff, stock levels, individual customers), set "unsupported_reason" explaining what data would be needed, and no steps.
Hypotheses are things to test, not conclusions. Keep purposes short.
TOOLS:
"""

REPORT_SYSTEM = """You are the interpretation module of OpsLens. You receive aggregated results from deterministic tools (evidence items E1, E2, ...).
Return ONE JSON object and nothing else:
{"executive_summary": str, "findings": [{"title": str, "text": str, "evidence_ids": ["E1"]}], "anomalies": [str], "implications": [str], "actions": [str],
 "confidence": {"level": "low|medium|high", "rationale": str}, "limitations": [str]}
STRICT RULES:
- Every number you write must appear in the evidence (you may round it). NEVER compute, sum, subtract, average or derive new numbers.
- Do not cite figures that are not in the evidence. Every finding must reference evidence ids.
- Revenue is not profit. Do not claim profit, ROI, productivity or stock insights. Distinguish correlation from causation; label explanations as hypotheses.
- Be concise and specific. State limitations honestly."""


class Emitter:
    def __init__(self):
        self.n = 0

    def __call__(self, type_: str, **data) -> dict:
        self.n += 1
        return {"seq": self.n, "ts": time.time(), "type": type_, **data}


async def run_investigation(*, engine: Engine, provider: Provider | None, question: str, history: list[HistoryItem] | None = None,
                            scenario: str | None = None) -> AsyncIterator[dict]:
    ev = Emitter()
    history = history or []
    yield ev("run_started", mode="ai" if provider else "scripted", scenario=scenario)

    # ---- plan
    if provider is None:
        if scenario not in SCENARIOS:
            yield ev("error", code="provider_not_configured",
                     message="No AI provider is configured (set ANTHROPIC_API_KEY or OPENAI_API_KEY). Free-form investigations need one; the preset scenarios still run with a scripted tool chain.")
            return
        q, steps = SCENARIOS[scenario]
        plan = Plan(objective=q, steps=[PlanStep(tool=t, args=a, purpose="Scripted scenario step (no AI provider configured)") for t, a in steps])
    else:
        yield ev("planning_started")
        user = json.dumps({"question": question, "previous_turns": [{"question": h.question, "summary": h.summary} for h in history[-3:]]})
        plan, err = None, None
        for attempt in range(2):
            try:
                raw = await provider.complete_json(PLAN_SYSTEM + json.dumps(tool_specs()), user + (f"\nYour previous output was invalid: {err}" if err else ""))
                plan = Plan.model_validate(extract_json(raw))
                if not (plan.steps or plan.clarification or plan.unsupported_reason):
                    raise ValueError("plan has no steps, clarification or unsupported_reason")
                break
            except ProviderError as ex:
                yield ev("error", code="provider_error", message=str(ex)); return
            except (ValueError, ValidationError) as ex:
                err, plan = str(ex)[:200], None
        if plan is None:
            yield ev("error", code="malformed_plan", message="The AI provider returned a plan that failed validation twice. Try rephrasing the question."); return

    yield ev("plan_created", plan=plan.model_dump())
    if plan.clarification:
        yield ev("clarification", question=plan.clarification); yield ev("done", status="needs_clarification"); return
    if plan.unsupported_reason and not plan.steps:
        yield ev("unsupported", reason=plan.unsupported_reason); yield ev("done", status="unsupported"); return

    # ---- execute tools
    evs: list[dict] = []
    for i, step in enumerate(plan.steps):
        cid = f"E{i + 1}"
        try:
            tool, model = validate_call(step.tool, step.args)
        except ToolError as ex:
            yield ev("tool_failed", call_id=cid, tool=step.tool[:60], stage="validation", error=str(ex)); continue
        args = model.model_dump(exclude_none=True)
        yield ev("tool_started", call_id=cid, tool=tool.name, args=args, purpose=step.purpose)
        t0 = time.perf_counter()
        try:
            result = await asyncio.to_thread(tool.fn, engine, model)
        except ToolError as ex:
            yield ev("tool_failed", call_id=cid, tool=tool.name, stage="execution", error=str(ex), duration_ms=round((time.perf_counter() - t0) * 1000, 1)); continue
        except Exception as ex:  # noqa: BLE001
            yield ev("tool_failed", call_id=cid, tool=tool.name, stage="execution", error=f"{type(ex).__name__}: {str(ex)[:160]}", duration_ms=round((time.perf_counter() - t0) * 1000, 1)); continue
        ms = round((time.perf_counter() - t0) * 1000, 1)
        evs.append({"id": cid, "tool": tool.name, "args": args, "result": result})
        yield ev("tool_finished", call_id=cid, tool=tool.name, args=args, duration_ms=ms, summary=result["metrics"],
                 table_rows={k: len(v) for k, v in result["tables"].items()}, result=result)
    if not evs:
        yield ev("error", code="no_evidence", message="No analytical tool completed successfully, so no report can be produced."); return

    # ---- interpret + validate
    if provider is None:
        report = deterministic_report(evs, f"Scripted '{scenario}' investigation: {len(evs)} of {len(plan.steps)} tools completed. Figures below are direct tool outputs.")
        yield ev("validation_result", ok=True, method="deterministic", unsupported_numbers=[])
    else:
        yield ev("interpretation_started", evidence_ids=[e["id"] for e in evs])
        pool = collect_numbers([e["result"] for e in evs]) + collect_numbers([h.evidence for h in history])
        valid_ids = {e["id"] for e in evs}
        payload = {"question": question, "objective": plan.objective, "hypotheses": plan.hypotheses,
                   "evidence": sanitize_for_llm([{"id": e["id"], "tool": e["tool"], "args": e["args"], **e["result"]} for e in evs]),
                   "previous_turns": [{"question": h.question, "summary": h.summary, "evidence": sanitize_for_llm(h.evidence)} for h in history[-2:]]}
        report, issues = None, None
        for attempt in range(2):
            try:
                raw = await provider.complete_json(REPORT_SYSTEM, json.dumps(payload) + (f"\nREJECTED: {issues}. Rewrite using only numbers present in the evidence." if issues else ""), 3500)
                cand = Report.model_validate(extract_json(raw))
                bad_ids = sorted({i for f in cand.findings for i in f.evidence_ids} - valid_ids)
                bad_nums = sorted({n for t in report_texts(cand) for n in find_unsupported(t, pool)})
                if bad_ids or bad_nums:
                    issues = f"unknown evidence ids {bad_ids}; unsupported numbers {bad_nums[:12]}"
                    yield ev("validation_result", ok=False, method="numeric_evidence_check", attempt=attempt + 1, unknown_evidence_ids=bad_ids, unsupported_numbers=bad_nums[:20])
                    continue
                report = cand.model_dump(); report["generated_by"] = "ai"
                yield ev("validation_result", ok=True, method="numeric_evidence_check", attempt=attempt + 1, unsupported_numbers=[])
                break
            except ProviderError as ex:
                yield ev("error", code="provider_error", message=str(ex)); return
            except (ValueError, ValidationError) as ex:
                issues = f"output failed schema validation: {str(ex)[:160]}"
                yield ev("validation_result", ok=False, method="schema_check", attempt=attempt + 1, error=issues)
        if report is None:
            report = deterministic_report(evs, "The AI interpretation was rejected twice because it contained unsupported figures or an invalid structure, so only the verified tool outputs are shown.")

    report["limitations"] = [*report.get("limitations", []), *DATA_LIMITATIONS]
    report["objective"] = plan.objective
    report["plan"] = plan.model_dump()
    report["tools_executed"] = [{"id": e["id"], "tool": e["tool"], "args": e["args"]} for e in evs]
    report["evidence"] = evs
    yield ev("report", report=report)
    yield ev("done", status="completed", tools_ok=len(evs), tools_planned=len(plan.steps))
