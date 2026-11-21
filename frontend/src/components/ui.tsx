"use client";
import { AlertTriangle, DatabaseZap, Download, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError, toolCsvUrl } from "@/lib/api";
import { fmtMetric, label } from "@/lib/format";

export function Panel({ title, action, children, className = "" }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel p-4 ${className}`}>
      {(title || action) && <div className="mb-3 flex items-center justify-between gap-2"><h3 className="panel-title">{title}</h3>{action}</div>}
      {children}
    </section>
  );
}
export const Chip = ({ tone = "muted", children }: { tone?: "ok" | "bad" | "warn" | "accent" | "muted"; children: ReactNode }) => {
  const t = { ok: "border-ok/30 bg-ok/10 text-ok", bad: "border-bad/30 bg-bad/10 text-bad", warn: "border-warn/30 bg-warn/10 text-warn", accent: "border-accent/40 bg-accent/10 text-accent-soft", muted: "border-ink-600 bg-ink-800 text-zinc-400" }[tone];
  return <span className={`chip ${t}`}>{children}</span>;
};
export const Loading = ({ text = "Loading from backend…" }: { text?: string }) => (
  <div role="status" className="flex items-center gap-2 py-8 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" />{text}</div>
);

/** Honest empty state: shown instead of any placeholder numbers. */
export function ErrorState({ error }: { error: ApiError | Error | string | null }) {
  const code = typeof error === "object" && error && "code" in error ? (error as ApiError).code : "";
  const msg = typeof error === "string" ? error : error?.message ?? "Unknown error";
  if (code === "dataset_not_ready") {
    return (
      <div className="panel border-warn/30 p-6" role="alert">
        <div className="mb-2 flex items-center gap-2 text-warn"><DatabaseZap className="h-5 w-5" /><b>Dataset not prepared</b></div>
        <p className="text-sm text-zinc-300">OpsLens shows only real, calculated figures, so nothing is displayed until the dataset is prepared.</p>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-ink-900 p-3 text-xs text-zinc-300">{`cd backend && pip install -r requirements.txt\npython -m opslens.ingest --download\n# or place online_retail_II.xlsx in data/raw/ then:\npython -m opslens.ingest`}</pre>
        <p className="mt-2 text-xs text-zinc-500">{msg}</p>
      </div>
    );
  }
  return (
    <div className="panel border-bad/30 p-4 text-sm" role="alert">
      <div className="flex items-center gap-2 text-bad"><AlertTriangle className="h-4 w-4" /><b>{code === "backend_unreachable" ? "Backend unreachable" : "Request failed"}</b></div>
      <p className="mt-1 text-zinc-400">{msg}</p>
    </div>
  );
}

export function Kpi({ name, value, sub, source }: { name: string; value: string; sub?: string; source?: string }) {
  return (
    <div className="panel p-4" title={source ? `Calculated by ${source}` : undefined}>
      <div className="panel-title">{name}</div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-zinc-50 tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

export function MetricsGrid({ metrics, limit }: { metrics: Record<string, string | number | null>; limit?: number }) {
  const rows = Object.entries(metrics).slice(0, limit);
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-3 border-b border-ink-700/60 py-1.5 text-sm">
          <dt className="text-zinc-500">{label(k)}</dt>
          <dd className="font-medium tabular-nums text-zinc-200">{fmtMetric(k, v)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function CsvLink({ tool, table }: { tool: string; table: string }) {
  return <a className="btn !px-2 !py-1 text-xs" href={toolCsvUrl(tool, table)} download><Download className="h-3 w-3" />CSV</a>;
}
export function SimpleTable({ rows, max = 10 }: { rows: Record<string, unknown>[]; max?: number }) {
  if (!rows.length) return <p className="text-sm text-zinc-500">No rows.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead><tr>{cols.map((c) => <th key={c} className="whitespace-nowrap border-b border-ink-700 px-2 py-1.5 font-medium text-zinc-500">{label(c)}</th>)}</tr></thead>
        <tbody>{rows.slice(0, max).map((r, i) => (
          <tr key={i} className="border-b border-ink-700/40">{cols.map((c) => <td key={c} className="whitespace-nowrap px-2 py-1.5 tabular-nums text-zinc-300">{fmtMetric(c, r[c] as string | number | null)}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}
