"use client";
import { ChevronDown, ChevronRight, FileDown, FileSpreadsheet, ShieldCheck, Sparkles, TerminalSquare } from "lucide-react";
import { useState } from "react";
import { sessionExportUrl } from "@/lib/api";
import type { Run, ToolRun } from "@/lib/investigation";
import { Chip, MetricsGrid, Panel, SimpleTable } from "./ui";
import { ToolChart, hasChart } from "./Charts";
import { Timeline } from "./Timeline";

export function ModeBadge({ mode }: { mode: Run["mode"] }) {
  if (mode === "ai") return <Chip tone="accent"><Sparkles className="h-3 w-3" />AI-powered investigation</Chip>;
  if (mode === "scripted") return <Chip tone="warn"><TerminalSquare className="h-3 w-3" />Scripted workflow (no AI)</Chip>;
  return null;
}

function ToolCard({ t, run }: { t: ToolRun; run: Run }) {
  const [open, setOpen] = useState(false);
  const tone = t.status === "ok" ? "ok" : t.status === "failed" ? "bad" : "accent";
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60" data-testid={`tool-${t.callId}`} data-status={t.status}>
      <button className="flex w-full items-center gap-2 px-3 py-2 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? <ChevronDown className="h-4 w-4 text-zinc-500" /> : <ChevronRight className="h-4 w-4 text-zinc-500" />}
        <span className="font-mono text-xs text-zinc-500">{t.callId}</span><span className="font-mono text-sm text-zinc-200">{t.tool}</span>
        <span className="ml-auto flex items-center gap-2">
          {t.durationMs !== undefined && <span className="font-mono text-[11px] text-zinc-500">{t.durationMs} ms</span>}
          <Chip tone={tone}>{t.status === "running" ? "running" : t.status === "ok" ? "succeeded" : `failed (${t.stage ?? "error"})`}</Chip>
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-ink-700 p-3">
          {t.purpose && <p className="text-xs text-zinc-400">{t.purpose}</p>}
          <div><div className="panel-title mb-1">Validated arguments</div><pre className="overflow-x-auto rounded bg-ink-950 p-2 font-mono text-[11px] text-zinc-400">{JSON.stringify(t.args, null, 1)}</pre></div>
          {t.error && <p className="rounded bg-bad/10 p-2 text-xs text-bad">{t.error}</p>}
          {t.result && (
            <>
              <div><div className="panel-title mb-1">Calculated metrics</div><MetricsGrid metrics={t.result.metrics} /></div>
              {hasChart(t.tool) && <ToolChart tool={t.tool} result={t.result} h={200} />}
              {Object.entries(t.result.tables).filter(([, r]) => r.length).map(([name, rows]) => (
                <div key={name}>
                  <div className="mb-1 flex items-center justify-between"><span className="panel-title">{name.replace(/_/g, " ")} ({rows.length} rows)</span>
                    {run.sessionId !== undefined && run.turn !== undefined && <a className="btn !px-2 !py-1 text-xs" href={sessionExportUrl(run.sessionId, run.turn, "csv", `?evidence=${t.callId}&table=${name}`)} download><FileSpreadsheet className="h-3 w-3" />CSV</a>}
                  </div>
                  <SimpleTable rows={rows} max={8} />
                </div>
              ))}
              {t.result.notes.map((n, i) => <p key={i} className="text-xs text-zinc-500">Note: {n}</p>)}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function ReportView({ run }: { run: Run }) {
  const r = run.report;
  if (!r) return null;
  const canExport = run.sessionId !== undefined && run.turn !== undefined;
  return (
    <Panel title="Investigation report" action={
      <div className="flex items-center gap-2">
        {canExport && <>
          <a className="btn" href={sessionExportUrl(run.sessionId!, run.turn!, "pdf")} download><FileDown className="h-4 w-4" />PDF</a>
          <a className="btn" href={sessionExportUrl(run.sessionId!, run.turn!, "csv")} download><FileSpreadsheet className="h-4 w-4" />Metrics CSV</a>
        </>}
      </div>}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {r.generated_by === "ai" ? <Chip tone="accent"><ShieldCheck className="h-3 w-3" />AI-interpreted, every figure checked against tool outputs</Chip>
          : <Chip tone="warn">Verified tool outputs, no AI interpretation</Chip>}
        <Chip tone={r.confidence.level === "high" ? "ok" : r.confidence.level === "medium" ? "warn" : "bad"}>Confidence: {r.confidence.level}</Chip>
      </div>
      <h4 className="text-sm font-semibold text-zinc-100">Executive summary</h4>
      <p className="mt-1 text-sm leading-relaxed text-zinc-300">{r.executive_summary}</p>
      <h4 className="mt-5 text-sm font-semibold text-zinc-100">Key findings</h4>
      <div className="mt-2 space-y-3">
        {r.findings.map((f, i) => (
          <div key={i} className="rounded-lg border border-ink-700 bg-ink-900/50 p-3">
            <div className="flex flex-wrap items-center gap-2"><b className="text-sm text-zinc-100">{f.title}</b>{f.evidence_ids.map((e) => <Chip key={e}>{e}</Chip>)}</div>
            <p className="mt-1 break-words text-sm text-zinc-400">{f.text}</p>
          </div>
        ))}
      </div>
      {([["Anomalies", r.anomalies], ["Business implications", r.implications], ["Recommended actions", r.actions]] as const).map(([t, items]) => items.length > 0 && (
        <div key={t}><h4 className="mt-5 text-sm font-semibold text-zinc-100">{t}</h4><ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-zinc-400">{items.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
      ))}
      <h4 className="mt-5 text-sm font-semibold text-zinc-100">Confidence</h4><p className="mt-1 text-sm text-zinc-400">{r.confidence.rationale}</p>
      <h4 className="mt-5 text-sm font-semibold text-zinc-100">Data limitations</h4>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-zinc-500">{r.limitations.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </Panel>
  );
}

export function RunView({ run }: { run: Run }) {
  const tools = run.toolOrder.map((id) => run.tools[id]);
  return (
    <article className="space-y-4" aria-label={`Investigation: ${run.question}`}>
      <div className="panel p-4">
        <div className="flex flex-wrap items-center gap-2"><ModeBadge mode={run.mode} />
          <Chip tone={run.status === "failed" ? "bad" : run.status === "completed" ? "ok" : "muted"}>{run.status.replace("_", " ")}</Chip>
        </div>
        <p className="mt-2 text-base font-medium text-zinc-100">{run.question}</p>
      </div>
      {run.error && <div role="alert" className="panel border-bad/30 p-4 text-sm"><b className="text-bad">{run.error.code}</b><p className="mt-1 text-zinc-400">{run.error.message}</p></div>}
      {run.clarification && <div className="panel border-accent/30 p-4 text-sm"><b className="text-accent-soft">The agent needs clarification</b><p className="mt-1 text-zinc-300">{run.clarification}</p></div>}
      {run.unsupported && <div className="panel border-warn/30 p-4 text-sm"><b className="text-warn">This dataset cannot answer that</b><p className="mt-1 text-zinc-300">{run.unsupported}</p></div>}
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-2">
          <Panel title="Live execution timeline"><Timeline items={run.timeline} startedAt={run.startedAt} /></Panel>
          {run.validation.length > 0 && (
            <Panel title="Evidence validation">
              <ul className="space-y-2 text-xs">{run.validation.map((v, i) => (
                <li key={i} className="flex items-start gap-2"><Chip tone={v.ok ? "ok" : "bad"}>{v.ok ? "passed" : "rejected"}</Chip><span className="text-zinc-400">{v.method.replace(/_/g, " ")}{v.attempt ? ` (attempt ${v.attempt})` : ""}{v.unsupported.length ? `, unsupported: ${v.unsupported.join(", ")}` : ""}</span></li>))}</ul>
            </Panel>
          )}
        </div>
        <div className="space-y-4 lg:col-span-3">
          {run.plan && (
            <Panel title="Investigation plan">
              <p className="text-sm text-zinc-200"><b>Objective:</b> {run.plan.objective}</p>
              {run.plan.questions.length > 0 && <><div className="panel-title mt-3">Questions</div><ul className="mt-1 list-disc pl-5 text-sm text-zinc-400">{run.plan.questions.map((q, i) => <li key={i}>{q}</li>)}</ul></>}
              {run.plan.hypotheses.length > 0 && <><div className="panel-title mt-3">Hypotheses to test</div><ul className="mt-1 list-disc pl-5 text-sm text-zinc-400">{run.plan.hypotheses.map((q, i) => <li key={i}>{q}</li>)}</ul></>}
              <div className="panel-title mt-3">Planned tool calls</div>
              <ol className="mt-1 list-decimal pl-5 font-mono text-xs text-zinc-400">{run.plan.steps.map((s, i) => <li key={i}>{s.tool}</li>)}</ol>
            </Panel>
          )}
          {tools.length > 0 && <Panel title={`Tool executions (${tools.length})`}><div className="space-y-2">{tools.map((t) => <ToolCard key={t.callId} t={t} run={run} />)}</div></Panel>}
        </div>
      </div>
      <ReportView run={run} />
    </article>
  );
}
