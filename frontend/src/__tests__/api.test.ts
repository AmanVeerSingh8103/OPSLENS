import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, parseSseChunk, runTool, streamInvestigation, clearToolCache } from "@/lib/api";
import { fmtMetric } from "@/lib/format";
import { frame, json, mockFetch, sseResponse } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); clearToolCache(); });

describe("SSE parser", () => {
  it("parses complete frames and keeps the partial remainder", () => {
    const a = frame({ seq: 1, type: "run_started" }), b = frame({ seq: 2, type: "plan_created" });
    const { events, rest } = parseSseChunk(a + b.slice(0, 12));
    expect(events.map((e) => e.type)).toEqual(["run_started"]);
    expect(parseSseChunk(rest + b.slice(12)).events[0].type).toBe("plan_created");
  });
  it("ignores malformed frames without throwing", () => {
    expect(parseSseChunk("data: {not json\n\n" + frame({ seq: 1, type: "done" })).events.map((e) => e.type)).toEqual(["done"]);
  });
  it("streams events in order even when the network splits frames mid-JSON", async () => {
    const frames = [1, 2, 3].map((n) => frame({ seq: n, type: "t" + n, ts: n }));
    mockFetch({ "/api/investigate": () => sseResponse(frames, 7) });
    const got: string[] = [];
    await streamInvestigation({ scenario: "revenue" }, (e) => got.push(e.type));
    expect(got).toEqual(["t1", "t2", "t3"]);
  });
});

describe("errors are surfaced honestly", () => {
  it("maps structured backend errors to ApiError with code", async () => {
    mockFetch({ "/api/investigate": () => json({ error: { code: "session_expired", message: "expired" } }, 410) });
    await expect(streamInvestigation({ question: "x", session_id: "s" }, () => {})).rejects.toMatchObject({ code: "session_expired", status: 410 });
  });
  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));
    await expect(runTool("get_dataset_overview")).rejects.toMatchObject({ code: "backend_unreachable" });
  });
  it("does not cache failures", async () => {
    let n = 0;
    mockFetch({ "/api/tools/x": () => (++n === 1 ? json({ error: { code: "dataset_not_ready", message: "no" } }, 503) : json({ result: { metrics: {}, tables: {}, notes: [] }, duration_ms: 1 })) });
    await expect(runTool("x")).rejects.toBeInstanceOf(ApiError);
    await expect(runTool("x")).resolves.toBeTruthy();
  });
  it("never sends an API key or history from the browser", async () => {
    const f = mockFetch({ "/api/investigate": () => sseResponse([]) });
    await streamInvestigation({ question: "hi", session_id: "abc" }, () => {});
    const body = JSON.parse((f.mock.calls[0][1] as RequestInit).body as string);
    expect(Object.keys(body).sort()).toEqual(["question", "session_id"]);
  });
});

describe("formatting", () => {
  it("shows n/a for unavailable values rather than inventing numbers", () => {
    expect(fmtMetric("sales_revenue", null)).toBe("n/a");
    expect(fmtMetric("x_pct", 12.345)).toBe("12.35%");
    expect(fmtMetric("sales_revenue", 1234.5)).toBe("£1,234.50");
    expect(fmtMetric("completed_invoices", 19960)).toBe("19,960");
  });
});
