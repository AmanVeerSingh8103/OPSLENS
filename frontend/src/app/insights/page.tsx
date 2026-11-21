"use client";
import { ToolChart } from "@/components/Charts";
import { PageHeader } from "@/components/Shell";
import { ErrorState, Loading, MetricsGrid, Panel } from "@/components/ui";
import { fmtMoney, fmtPct } from "@/lib/format";
import { useTool, type ToolState } from "@/lib/useTool";

function Insight({ title, tool, args, st, headline }: { title: string; tool: string; args?: Record<string, unknown>; st: ToolState; headline: (m: Record<string, string | number | null>, t: NonNullable<ToolState["data"]>["tables"]) => string }) {
  return (
    <Panel title={title}>
      {st.error ? <ErrorState error={st.error} /> : !st.data ? <Loading /> : (
        <div data-testid="insight">
          <p className="text-base font-medium leading-snug text-zinc-100">{headline(st.data.metrics, st.data.tables)}</p>
          <div className="mt-3"><ToolChart tool={tool} result={st.data} h={180} /></div>
          <details className="mt-3"><summary className="cursor-pointer text-xs text-zinc-500">Supporting calculation: <span className="font-mono">{tool}</span> {args ? JSON.stringify(args) : ""}{st.durationMs !== undefined ? ` (${st.durationMs} ms)` : ""}</summary>
            <div className="mt-2"><MetricsGrid metrics={st.data.metrics} /></div>
            {st.data.notes.map((n, i) => <p key={i} className="mt-1 text-xs text-zinc-600">{n}</p>)}</details>
        </div>
      )}
    </Panel>
  );
}

export default function Insights() {
  const conc = useTool("get_product_concentration");
  const prod = useTool("get_product_performance", { top_n: 5 });
  const canc = useTool("get_cancellation_analysis", { top_n: 5 });
  const ctry = useTool("get_country_performance", { top_n: 5 });
  const seas = useTool("get_seasonality_analysis");
  const anom = useTool("get_anomaly_summary", { granularity: "day", z_threshold: 3 });
  const trend = useTool("get_revenue_trend");
  return (
    <>
      <PageHeader title="Insights" sub="Automatically calculated. Each headline is generated from the returned figures; expand it to see the supporting calculation. Statements describe association, not causation." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Insight title="Revenue concentration" tool="get_product_concentration" st={conc} headline={(m) => m.top_10_share_pct == null ? "Concentration unavailable." : `The top 10 products generate ${fmtPct(m.top_10_share_pct)} of revenue; ${m.products_for_80pct_revenue} products account for 80%.`} />
        <Insight title="Product performance changes" tool="get_product_performance" args={{ top_n: 5 }} st={prod} headline={(_, t) => { const d = t.declining_products?.[0]; return d ? `${String(d.description ?? d.stock_code)} fell ${fmtPct(Math.abs(Number(d.change_pct)))} (${fmtMoney(Number(d.prior_revenue), true)} → ${fmtMoney(Number(d.recent_revenue), true)}) between the two most recent half-year windows.` : "Not enough history to compare product performance windows."; }} />
        <Insight title="Cancellation patterns" tool="get_cancellation_analysis" args={{ top_n: 5 }} st={canc} headline={(m, t) => `${fmtPct(m.cancellation_invoice_rate_pct)} of invoices are cancellations${t.peak_months?.[0] ? `; the peak month was ${t.peak_months[0].year_month}` : ""}.`} />
        <Insight title="Geographic performance" tool="get_country_performance" args={{ top_n: 5 }} st={ctry} headline={(m) => `${m.top_country} contributes ${fmtPct(m.top_country_share_pct)} of revenue; the top 5 markets together contribute ${fmtPct(m.top_n_share_pct)}.`} />
        <Insight title="Seasonal trends" tool="get_seasonality_analysis" st={seas} headline={(m) => m.peak_calendar_month == null ? "Seasonality unavailable." : `Calendar month ${m.peak_calendar_month} is the seasonal peak (index ${m.peak_seasonal_index}); month ${m.trough_calendar_month} is the trough (index ${m.trough_seasonal_index}).`} />
        <Insight title="Unusual activity" tool="get_anomaly_summary" args={{ granularity: "day", z_threshold: 3 }} st={anom} headline={(m, t) => `${m.anomalies_found} of ${m.periods_analysed} days exceed ±3σ${t.anomalies?.[0] ? `; the largest is ${t.anomalies[0].period}` : ""}.`} />
        <Insight title="Revenue declines" tool="get_revenue_trend" st={trend} headline={(m, t) => `${m.significant_declines} month${m.significant_declines === 1 ? "" : "s"} had a revenue drop of ${m.decline_threshold_pct}% or more month-over-month${t.significant_declines?.[0] ? ` (first: ${t.significant_declines[0].year_month})` : ""}.`} />
      </div>
    </>
  );
}
