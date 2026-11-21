import type { SseEvent, ToolResult } from "./api";

export type ToolStatus = "running" | "ok" | "failed";
export interface ToolRun {
  callId: string; tool: string; args: Record<string, unknown>; purpose?: string; status: ToolStatus;
  durationMs?: number; summary?: ToolResult["metrics"]; result?: ToolResult; error?: string; stage?: string;
}
export interface TimelineItem {
  key: string; kind: "run" | "plan" | "tool" | "interpret" | "validate" | "report" | "note" | "error";
  label: string; status: "info" | "running" | "ok" | "failed"; detail?: string; ts: number; callId?: string;
}
export interface Plan { objective: string; questions: string[]; hypotheses: string[]; steps: { tool: string; args: Record<string, unknown>; purpose: string }[]; clarification?: string | null; unsupported_reason?: string | null }
export interface Finding { title: string; text: string; evidence_ids: string[] }
export interface Report {
  executive_summary: string; findings: Finding[]; anomalies: string[]; implications: string[]; actions: string[];
  confidence: { level: "low" | "medium" | "high"; rationale: string }; limitations: string[]; generated_by: "ai" | "deterministic";
  objective: string; plan: Plan; tools_executed: { id: string; tool: string; args: Record<string, unknown> }[];
  evidence: { id: string; tool: string; args: Record<string, unknown>; result: ToolResult }[];
}
export type RunStatus = "starting" | "running" | "completed" | "failed" | "needs_clarification" | "unsupported";

export interface Run {
  id: string; question: string; scenario?: string; mode: "ai" | "scripted" | null; status: RunStatus;
  timeline: TimelineItem[]; tools: Record<string, ToolRun>; toolOrder: string[]; plan?: Plan; report?: Report;
  sessionId?: string; turn?: number; error?: { code: string; message: string }; clarification?: string; unsupported?: string;
  validation: { ok: boolean; method: string; attempt?: number; unsupported: string[]; unknownIds: string[] }[];
  eventCount: number; startedAt?: number; endedAt?: number; rawEvents: SseEvent[];
}

export const newRun = (id: string, question: string, scenario?: string): Run => ({
  id, question, scenario, mode: null, status: "starting", timeline: [], tools: {}, toolOrder: [], validation: [], eventCount: 0, rawEvents: [],
});

const upsert = (tl: TimelineItem[], item: TimelineItem) => {
  const i = tl.findIndex((t) => t.key === item.key);
  return i < 0 ? [...tl, item] : tl.map((t, j) => (j === i ? { ...t, ...item } : t));
};

/** Pure reducer. State changes ONLY in response to an event received from the backend. */
export function applyEvent(run: Run, ev: SseEvent): Run {
  const base: Run = { ...run, eventCount: run.eventCount + 1, rawEvents: [...run.rawEvents, ev], startedAt: run.startedAt ?? ev.ts };
  switch (ev.type) {
    case "run_started":
      return { ...base, status: "running", mode: ev.mode, timeline: upsert(base.timeline, { key: "run", kind: "run", status: "ok", ts: ev.ts,
        label: ev.mode === "ai" ? "Run started: AI-powered investigation" : "Run started: scripted analytical workflow (no AI provider)" }) };
    case "planning_started":
      return { ...base, timeline: upsert(base.timeline, { key: "plan", kind: "plan", status: "running", ts: ev.ts, label: "Asking the AI provider for an investigation plan" }) };
    case "plan_created":
      return { ...base, plan: ev.plan, timeline: upsert(base.timeline, { key: "plan", kind: "plan", status: "ok", ts: ev.ts, label: "Investigation plan created",
        detail: `${ev.plan.steps.length} planned tool call${ev.plan.steps.length === 1 ? "" : "s"}` }) };
    case "clarification":
      return { ...base, clarification: ev.question, timeline: upsert(base.timeline, { key: "clar", kind: "note", status: "info", ts: ev.ts, label: "Agent needs clarification", detail: ev.question }) };
    case "unsupported":
      return { ...base, unsupported: ev.reason, timeline: upsert(base.timeline, { key: "unsup", kind: "note", status: "info", ts: ev.ts, label: "Question not answerable with this dataset", detail: ev.reason }) };
    case "tool_started": {
      const t: ToolRun = { callId: ev.call_id, tool: ev.tool, args: ev.args, purpose: ev.purpose, status: "running" };
      return { ...base, tools: { ...base.tools, [ev.call_id]: t }, toolOrder: base.toolOrder.includes(ev.call_id) ? base.toolOrder : [...base.toolOrder, ev.call_id],
        timeline: upsert(base.timeline, { key: `tool-${ev.call_id}`, kind: "tool", status: "running", ts: ev.ts, callId: ev.call_id, label: `Executing ${ev.tool}` }) };
    }
    case "tool_finished": {
      const t: ToolRun = { ...(base.tools[ev.call_id] ?? { callId: ev.call_id, tool: ev.tool, args: ev.args }), status: "ok", durationMs: ev.duration_ms, summary: ev.summary, result: ev.result };
      return { ...base, tools: { ...base.tools, [ev.call_id]: t }, toolOrder: base.toolOrder.includes(ev.call_id) ? base.toolOrder : [...base.toolOrder, ev.call_id],
        timeline: upsert(base.timeline, { key: `tool-${ev.call_id}`, kind: "tool", status: "ok", ts: ev.ts, callId: ev.call_id, label: `${ev.tool} returned`, detail: `${ev.duration_ms} ms` }) };
    }
    case "tool_failed": {
      const t: ToolRun = { ...(base.tools[ev.call_id] ?? { callId: ev.call_id, tool: ev.tool, args: {} }), status: "failed", error: ev.error, stage: ev.stage, durationMs: ev.duration_ms };
      return { ...base, tools: { ...base.tools, [ev.call_id]: t }, toolOrder: base.toolOrder.includes(ev.call_id) ? base.toolOrder : [...base.toolOrder, ev.call_id],
        timeline: upsert(base.timeline, { key: `tool-${ev.call_id}`, kind: "tool", status: "failed", ts: ev.ts, callId: ev.call_id, label: `${ev.tool} failed (${ev.stage})`, detail: ev.error }) };
    }
    case "interpretation_started":
      return { ...base, timeline: upsert(base.timeline, { key: "interp", kind: "interpret", status: "running", ts: ev.ts, label: "AI interpreting aggregated tool results" }) };
    case "validation_result": {
      const v = { ok: !!ev.ok, method: ev.method, attempt: ev.attempt, unsupported: ev.unsupported_numbers ?? [], unknownIds: ev.unknown_evidence_ids ?? [] };
      const n = base.validation.length;
      return { ...base, validation: [...base.validation, v], timeline: upsert(
        ev.method === "deterministic" ? base.timeline : upsert(base.timeline, { key: "interp", kind: "interpret", status: "ok", ts: ev.ts, label: "AI interpretation received" }),
        { key: `val-${n}`, kind: "validate", status: v.ok ? "ok" : "failed", ts: ev.ts,
          label: v.ok ? "Numerical claims verified against tool outputs" : "Output rejected by evidence validation",
          detail: v.ok ? undefined : [v.unsupported.length ? `Unsupported figures: ${v.unsupported.join(", ")}` : "", v.unknownIds.length ? `Unknown evidence ids: ${v.unknownIds.join(", ")}` : "", ev.error ?? ""].filter(Boolean).join(" | ") }) };
    }
    case "report":
      return { ...base, report: ev.report, sessionId: ev.session_id, turn: ev.turn, timeline: upsert(base.timeline, { key: "report", kind: "report", status: "ok", ts: ev.ts,
        label: ev.report.generated_by === "ai" ? "Report generated (AI-interpreted, evidence-checked)" : "Report generated from verified tool outputs" }) };
    case "error":
      return { ...base, status: "failed", error: { code: ev.code, message: ev.message }, endedAt: ev.ts, timeline: upsert(base.timeline, { key: "error", kind: "error", status: "failed", ts: ev.ts, label: `Error: ${ev.code}`, detail: ev.message }) };
    case "done":
      return { ...base, endedAt: ev.ts, status: ev.status === "needs_clarification" ? "needs_clarification" : ev.status === "unsupported" ? "unsupported" : "completed" };
    default:
      return base;
  }
}

/** Transport-level failure (HTTP error before any event): shown honestly, no synthetic timeline. */
export const failRun = (run: Run, code: string, message: string): Run => ({ ...run, status: "failed", error: { code, message } });
