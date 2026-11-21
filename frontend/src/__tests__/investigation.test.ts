import { describe, expect, it } from "vitest";
import type { SseEvent } from "@/lib/api";
import { applyEvent, failRun, newRun, type Run } from "@/lib/investigation";

const E = (type: string, extra: object = {}, seq = 1): SseEvent => ({ seq, ts: 1000 + seq, type, ...extra });
const fold = (evs: SseEvent[]) => evs.reduce<Run>((r, e) => applyEvent(r, e), newRun("r", "q"));
const result = { metrics: { revenue: 10 }, tables: { monthly: [{ year_month: "2010-01", revenue: 10 }] }, notes: [] };

describe("timeline reflects only received events", () => {
  it("a run with no events has an empty timeline", () => { expect(newRun("r", "q").timeline).toEqual([]); });

  it("a tool is 'running' after tool_started and only 'ok' after tool_finished", () => {
    const started = fold([E("run_started", { mode: "scripted" }), E("tool_started", { call_id: "E1", tool: "get_revenue_trend", args: {} }, 2)]);
    expect(started.tools.E1.status).toBe("running");
    expect(started.timeline.find((t) => t.callId === "E1")!.status).toBe("running");
    const done = applyEvent(started, E("tool_finished", { call_id: "E1", tool: "get_revenue_trend", args: {}, duration_ms: 12.5, summary: { revenue: 10 }, result }, 3));
    expect(done.tools.E1).toMatchObject({ status: "ok", durationMs: 12.5 });
    expect(done.timeline.find((t) => t.callId === "E1")).toMatchObject({ status: "ok", detail: "12.5 ms" });
  });

  it("a failed tool is shown as failed with the backend's error and never as ok", () => {
    const r = fold([E("run_started", { mode: "ai" }), E("tool_failed", { call_id: "E2", tool: "run_sql", stage: "validation", error: "Unknown tool 'run_sql'" }, 2)]);
    expect(r.tools.E2.status).toBe("failed");
    expect(r.timeline.find((t) => t.callId === "E2")).toMatchObject({ status: "failed", detail: "Unknown tool 'run_sql'" });
    expect(r.timeline.some((t) => t.status === "ok" && t.callId === "E2")).toBe(false);
  });

  it("preserves backend ordering and one row per tool call", () => {
    const r = fold([E("run_started", { mode: "scripted" }), E("tool_started", { call_id: "E1", tool: "a", args: {} }, 2), E("tool_finished", { call_id: "E1", tool: "a", args: {}, duration_ms: 1, summary: {}, result }, 3),
      E("tool_started", { call_id: "E2", tool: "b", args: {} }, 4), E("tool_finished", { call_id: "E2", tool: "b", args: {}, duration_ms: 1, summary: {}, result }, 5)]);
    expect(r.toolOrder).toEqual(["E1", "E2"]);
    expect(r.timeline.filter((t) => t.kind === "tool")).toHaveLength(2);
  });

  it("evidence-validation rejection is displayed as rejected with the offending figures", () => {
    const r = fold([E("interpretation_started"), E("validation_result", { ok: false, method: "numeric_evidence_check", attempt: 1, unsupported_numbers: ["87.65%"], unknown_evidence_ids: [] }, 2)]);
    expect(r.validation[0]).toMatchObject({ ok: false, unsupported: ["87.65%"] });
    expect(r.timeline.find((t) => t.kind === "validate")).toMatchObject({ status: "failed" });
    expect(r.timeline.find((t) => t.kind === "validate")!.detail).toContain("87.65%");
  });

  it("deterministic validation does not claim an AI interpretation happened", () => {
    const r = fold([E("run_started", { mode: "scripted" }), E("validation_result", { ok: true, method: "deterministic", unsupported_numbers: [] }, 2)]);
    expect(r.timeline.some((t) => t.kind === "interpret")).toBe(false);
  });

  it("error event fails the run; report event records session and turn", () => {
    expect(fold([E("error", { code: "provider_error", message: "down" })])).toMatchObject({ status: "failed", error: { code: "provider_error" } });
    const rep = fold([E("report", { report: { generated_by: "ai" }, session_id: "S", turn: 2 }), E("done", { status: "completed" }, 2)]);
    expect(rep).toMatchObject({ sessionId: "S", turn: 2, status: "completed" });
  });

  it("clarification and unsupported end the run without tools", () => {
    expect(fold([E("clarification", { question: "Which period?" }), E("done", { status: "needs_clarification" }, 2)])).toMatchObject({ status: "needs_clarification", clarification: "Which period?" });
    expect(fold([E("unsupported", { reason: "No cost data" }), E("done", { status: "unsupported" }, 2)]).toolOrder).toEqual([]);
  });

  it("transport failure creates no synthetic timeline", () => {
    const r = failRun(newRun("r", "q"), "backend_unreachable", "nope");
    expect(r.timeline).toEqual([]); expect(r.status).toBe("failed");
  });
});
