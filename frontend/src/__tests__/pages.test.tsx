import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Investigations from "@/app/investigations/page";
import Overview from "@/app/page";
import Reports from "@/app/reports/page";
import { clearToolCache } from "@/lib/api";
import { AppProvider } from "@/lib/store";
import { frame, json, mockFetch, sseResponse, SCENARIOS, STATUS } from "./helpers";

const OV = { metrics: { total_records: 777, completed_invoices: 123, cancellation_invoices: 45, sales_revenue: 98765.43, unique_products: 67, countries: 8, average_invoice_value: 802.97, first_date: "2010-01-04", last_date: "2011-12-09" }, tables: {}, notes: [] };
const MONTHLY = [{ year_month: "2010-01", revenue: 100, invoices: 3 }, { year_month: "2010-02", revenue: 80, invoices: 2 }];
const tool = (r: object) => () => json({ tool: "t", duration_ms: 1, result: { metrics: {}, tables: {}, notes: [], ...r } });

beforeEach(() => clearToolCache());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Overview", () => {
  it("renders KPIs exactly as returned by the backend", async () => {
    mockFetch({ "get_dataset_overview": tool(OV), "get_revenue_trend": tool({ tables: { monthly: MONTHLY } }), "get_country_performance": tool({ tables: { countries: [{ country: "UK", revenue: 5 }] } }),
      "get_product_performance": tool({ tables: { top_products: [{ stock_code: "1", revenue: 5 }] } }), "get_cancellation_analysis": tool({ tables: { monthly: [] } }), "/api/status": () => json(STATUS()), "/api/scenarios": () => json(SCENARIOS) });
    render(<AppProvider><Overview /></AppProvider>);
    const k = await screen.findByTestId("kpis");
    for (const v of ["777", "123", "45", "£98,765.43", "67", "£802.97", "2010-01-04 → 2011-12-09"]) expect(k).toHaveTextContent(v);
  });
  it("shows setup instructions and NO figures when the dataset is not prepared", async () => {
    mockFetch({ "/api/tools": () => json({ error: { code: "dataset_not_ready", message: "Processed dataset not found." } }, 503), "/api/status": () => json(STATUS({ ready: false })), "/api/scenarios": () => json(SCENARIOS) });
    render(<AppProvider><Overview /></AppProvider>);
    expect(await screen.findByText("Dataset not prepared")).toBeInTheDocument();
    expect(screen.getByText(/python -m opslens.ingest --download/)).toBeInTheDocument();
    expect(screen.queryByTestId("kpis")).toBeNull();
  });
  it("shows a backend-unreachable error instead of fake data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("x"); }));
    render(<AppProvider><Overview /></AppProvider>);
    expect(await screen.findByText("Backend unreachable")).toBeInTheDocument();
  });
});

const PLAN = { objective: "Revenue", questions: [], hypotheses: [], steps: [{ tool: "get_revenue_trend", args: {}, purpose: "" }, { tool: "bad_tool", args: {}, purpose: "" }] };
const REPORT = { executive_summary: "Summary text.", findings: [{ title: "F1", text: "Finding text", evidence_ids: ["E1"] }], anomalies: [], implications: [], actions: [], confidence: { level: "medium", rationale: "r" }, limitations: ["Revenue is not profit."], generated_by: "deterministic", objective: "Revenue", plan: PLAN, tools_executed: [], evidence: [] };
const RUN_FRAMES = [
  frame({ seq: 1, ts: 1, type: "run_started", mode: "scripted", scenario: "revenue" }), frame({ seq: 2, ts: 2, type: "plan_created", plan: PLAN }),
  frame({ seq: 3, ts: 3, type: "tool_started", call_id: "E1", tool: "get_revenue_trend", args: {}, purpose: "" }),
  frame({ seq: 4, ts: 4, type: "tool_finished", call_id: "E1", tool: "get_revenue_trend", args: {}, duration_ms: 9.1, summary: { months: 2 }, result: { metrics: { months: 2 }, tables: { monthly: MONTHLY }, notes: [] } }),
  frame({ seq: 5, ts: 5, type: "tool_failed", call_id: "E2", tool: "bad_tool", stage: "validation", error: "Unknown tool 'bad_tool'." }),
  frame({ seq: 6, ts: 6, type: "validation_result", ok: true, method: "deterministic", unsupported_numbers: [] }),
  frame({ seq: 7, ts: 7, type: "report", report: REPORT, session_id: "SESS123", turn: 0 }), frame({ seq: 8, ts: 8, type: "done", status: "completed" }),
];

describe("Investigations", () => {
  it("without an AI provider: explains honestly, disables free text, offers scripted scenarios", async () => {
    mockFetch({ "/api/status": () => json(STATUS({ ai: false })), "/api/scenarios": () => json(SCENARIOS) });
    render(<AppProvider><Investigations /></AppProvider>);
    expect(await screen.findByTestId("no-ai")).toHaveTextContent(/will not pretend to answer them/);
    expect(screen.queryByLabelText("Investigation question")).toBeNull();
    expect(await screen.findByText("revenue investigation")).toBeInTheDocument();
    expect(screen.getByText(/scripted analytical workflows/)).toBeInTheDocument();
  });
  it("with an AI provider: free-text input is available and discloses what is sent", async () => {
    mockFetch({ "/api/status": () => json(STATUS({ ai: true })), "/api/scenarios": () => json(SCENARIOS) });
    render(<AppProvider><Investigations /></AppProvider>);
    expect(await screen.findByLabelText("Investigation question")).toBeInTheDocument();
    expect(screen.getByText(/never raw transactions or customer identifiers/)).toBeInTheDocument();
  });
  it("runs a scenario from real SSE events: ok tool, honestly failed tool, report with exports tied to the server session", async () => {
    const f = mockFetch({ "/api/status": () => json(STATUS()), "/api/scenarios": () => json(SCENARIOS), "/api/investigate": () => sseResponse(RUN_FRAMES, 40) });
    render(<AppProvider><Investigations /></AppProvider>);
    fireEvent.click(await screen.findByText("revenue investigation"));
    const tl = await screen.findByRole("list", { name: "Execution timeline" });
    await waitFor(() => expect(within(tl).getByText(/get_revenue_trend returned/)).toBeInTheDocument());
    expect(within(tl).getByText(/bad_tool failed \(validation\)/)).toBeInTheDocument();
    expect(tl.querySelector('[data-status="failed"]')).not.toBeNull();
    expect(screen.getByTestId("tool-E1")).toHaveAttribute("data-status", "ok");
    expect(screen.getByTestId("tool-E2")).toHaveAttribute("data-status", "failed");
    expect(screen.getAllByText(/Scripted workflow \(no AI\)/).length).toBeGreaterThan(0);
    expect(await screen.findByText("Summary text.")).toBeInTheDocument();
    const pdf = screen.getByRole("link", { name: /PDF/ });
    expect(pdf.getAttribute("href")).toMatch(/\/api\/sessions\/SESS123\/turns\/0\/export\.pdf$/);
    const body = JSON.parse((f.mock.calls.find((c) => String(c[0]).includes("/api/investigate"))![1] as RequestInit).body as string);
    expect(body).toEqual({ scenario: "revenue" });
  });
  it("shows a transport error without inventing a timeline", async () => {
    mockFetch({ "/api/status": () => json(STATUS()), "/api/scenarios": () => json(SCENARIOS), "/api/investigate": () => json({ error: { code: "rate_limited", message: "Too many requests." } }, 429) });
    render(<AppProvider><Investigations /></AppProvider>);
    fireEvent.click(await screen.findByText("revenue investigation"));
    expect(await screen.findByText("rate_limited")).toBeInTheDocument();
    expect(screen.getByText(/Waiting for the first backend event/)).toBeInTheDocument();
  });
  it("reports page lists this session's reports and links exports", async () => {
    mockFetch({ "/api/status": () => json(STATUS()), "/api/scenarios": () => json(SCENARIOS), "/api/investigate": () => sseResponse(RUN_FRAMES) });
    const Both = () => <AppProvider><Investigations /><Reports /></AppProvider>;
    render(<Both />);
    fireEvent.click(await screen.findByText("revenue investigation"));
    await waitFor(() => expect(screen.getAllByText("Summary text.").length).toBe(2));
    expect(screen.getAllByRole("link", { name: /Metrics CSV/ }).length).toBeGreaterThan(0);
  });
});
