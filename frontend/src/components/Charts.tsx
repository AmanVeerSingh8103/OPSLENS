"use client";
import { Bar, BarChart, CartesianGrid, ComposedChart, Area, AreaChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ToolResult } from "@/lib/api";
import { fmtInt, fmtMoney, fmtPct } from "@/lib/format";

const AX = { stroke: "#52526b", fontSize: 11, tickLine: false, axisLine: false } as const;
const TT = { contentStyle: { background: "#0f0f17", border: "1px solid #2a2a3b", borderRadius: 8, fontSize: 12 }, labelStyle: { color: "#a1a1b5" }, cursor: { fill: "rgba(124,108,246,0.08)" } };
type Row = Record<string, string | number | boolean | null>;
const Box = ({ h = 220, children }: { h?: number; children: React.ReactElement }) => <div style={{ height: h }} className="w-full"><ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer></div>;
const compact = (v: number) => fmtMoney(v, true);

export function TrendChart({ rows, y = "revenue", fmt = compact, h }: { rows: Row[]; y?: string; fmt?: (v: number) => string; h?: number }) {
  return (
    <Box h={h}>
      <AreaChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
        <defs><linearGradient id={`g-${y}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7c6cf6" stopOpacity={0.45} /><stop offset="100%" stopColor="#7c6cf6" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="#1c1c29" vertical={false} />
        <XAxis dataKey="year_month" {...AX} interval="preserveStartEnd" minTickGap={28} />
        <YAxis {...AX} tickFormatter={(v) => fmt(v as number)} width={56} />
        <Tooltip {...TT} formatter={(v) => [fmt(v as number), y.replace(/_/g, " ")]} />
        <Area type="monotone" dataKey={y} stroke="#8b7dff" strokeWidth={2} fill={`url(#g-${y})`} />
      </AreaChart>
    </Box>
  );
}
export function BarsChart({ rows, x, y, fmt = compact, h, color = "#6d5ef5", horizontal = false }: { rows: Row[]; x: string; y: string; fmt?: (v: number) => string; h?: number; color?: string; horizontal?: boolean }) {
  return (
    <Box h={h}>
      <BarChart data={rows} layout={horizontal ? "vertical" : "horizontal"} margin={{ left: horizontal ? 24 : 0, right: 8, top: 8 }}>
        <CartesianGrid stroke="#1c1c29" horizontal={!horizontal} vertical={horizontal} />
        {horizontal
          ? (<><XAxis type="number" {...AX} tickFormatter={(v) => fmt(v as number)} /><YAxis type="category" dataKey={x} {...AX} width={96} /></>)
          : (<><XAxis dataKey={x} {...AX} interval={0} tick={{ fontSize: 10, fill: "#52526b" }} /><YAxis {...AX} tickFormatter={(v) => fmt(v as number)} width={56} /></>)}
        <Tooltip {...TT} formatter={(v) => [fmt(v as number), y.replace(/_/g, " ")]} />
        <Bar dataKey={y} fill={color} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} />
      </BarChart>
    </Box>
  );
}
export function CancellationChart({ rows, h }: { rows: Row[]; h?: number }) {
  return (
    <Box h={h}>
      <ComposedChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid stroke="#1c1c29" vertical={false} />
        <XAxis dataKey="year_month" {...AX} interval="preserveStartEnd" minTickGap={28} />
        <YAxis yAxisId="l" {...AX} tickFormatter={(v) => fmtInt(v)} width={44} />
        <YAxis yAxisId="r" orientation="right" {...AX} tickFormatter={(v) => `${v}%`} width={40} />
        <Tooltip {...TT} formatter={(v, n) => [n === "cancellation_rate_pct" ? fmtPct(v) : fmtInt(v), String(n).replace(/_/g, " ")]} />
        <Bar yAxisId="l" dataKey="cancellation_invoices" fill="#4f8cff" radius={[3, 3, 0, 0]} />
        <Line yAxisId="r" type="monotone" dataKey="cancellation_rate_pct" stroke="#f87171" strokeWidth={2} dot={false} />
      </ComposedChart>
    </Box>
  );
}

/** Picks the right visual for a tool result. Every plotted point comes straight from the tool's returned tables. */
export function ToolChart({ tool, result, h }: { tool: string; result: ToolResult; h?: number }) {
  const t = result.tables;
  switch (tool) {
    case "get_revenue_trend": return t.monthly?.length ? <TrendChart rows={t.monthly} h={h} /> : null;
    case "get_average_invoice_value": return t.monthly?.length ? <TrendChart rows={t.monthly} y="average_invoice_value" fmt={(v) => fmtMoney(v)} h={h} /> : null;
    case "get_quantity_analysis": return t.monthly_units?.length ? <TrendChart rows={t.monthly_units} y="units" fmt={fmtInt} h={h} /> : null;
    case "get_country_performance": return t.countries?.length ? <BarsChart rows={t.countries} x="country" y="revenue" horizontal h={h ?? 260} /> : null;
    case "get_product_performance": return t.top_products?.length ? <BarsChart rows={t.top_products} x="stock_code" y="revenue" h={h} /> : null;
    case "get_cancellation_analysis": return t.monthly?.length ? <CancellationChart rows={t.monthly} h={h} /> : null;
    case "get_seasonality_analysis": return t.calendar_month_index?.length ? <BarsChart rows={t.calendar_month_index} x="calendar_month" y="seasonal_index" fmt={(v) => v.toFixed(2)} color="#4f8cff" h={h} /> : null;
    case "get_anomaly_summary": return t.anomalies?.length ? <BarsChart rows={t.anomalies} x="period" y="z_score" fmt={(v) => v.toFixed(1)} color="#fbbf24" h={h} /> : null;
    case "get_top_bottom_performers": return t.top?.length ? <BarsChart rows={t.top} x={Object.keys(t.top[0])[0]} y="revenue" h={h} /> : null;
    default: return null;
  }
}
export const hasChart = (tool: string) => ["get_revenue_trend", "get_average_invoice_value", "get_quantity_analysis", "get_country_performance", "get_product_performance", "get_cancellation_analysis", "get_seasonality_analysis", "get_anomaly_summary", "get_top_bottom_performers"].includes(tool);
