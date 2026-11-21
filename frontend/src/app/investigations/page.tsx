"use client";
import { Bot, Lock, Play, RotateCcw, Send, Square, TerminalSquare } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { RunView } from "@/components/RunView";
import { Chip, Panel } from "@/components/ui";
import { useApp } from "@/lib/store";

const SUGGESTED = [
  "Why did revenue fall in some months, and which markets drove it?",
  "Which products are losing revenue recently, and how concentrated is our revenue?",
  "Is there anything unusual in daily sales activity?",
];

export default function Investigations() {
  const { status, statusError, scenarios, runs, busy, start, reset, cancel, sessionId } = useApp();
  const [q, setQ] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const ai = !!status?.ai_configured;
  const ready = !!status?.dataset_ready;
  useEffect(() => { if (runs.length) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [runs.length]);
  const submit = () => { if (!q.trim() || busy || !ai) return; const t = q; setQ(""); void start({ question: t }); };
  const followUp = ai && sessionId && runs.length > 0;

  return (
    <>
      <PageHeader title="Investigations" sub="Ask a business question. The agent plans, runs real analytical tools against the dataset, and reports only what the calculations support."
        right={runs.length > 0 ? <button className="btn" onClick={reset}><RotateCcw className="h-4 w-4" />New investigation</button> : undefined} />
      {statusError && <div role="alert" className="panel mb-4 border-bad/30 p-4 text-sm text-bad">{statusError}</div>}
      {status && !ready && <div role="alert" className="panel mb-4 border-warn/30 p-4 text-sm text-warn">{status.dataset_message}</div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Preset scenarios" className="lg:col-span-2">
          <p className="mb-3 text-xs text-zinc-500">
            {ai ? "Presets run the same real tools as a scripted workflow; use the question box for full AI-planned investigations."
              : "No AI provider is configured, so presets run as scripted analytical workflows: fixed tool chains executing real calculations, with no AI planning or interpretation."}
          </p>
          <div className="grid gap-2 sm:grid-cols-2" data-testid="scenarios">
            {scenarios.map((s) => (
              <button key={s.id} disabled={busy || !ready} onClick={() => void start({ scenario: s.id })}
                className="group flex items-start gap-3 rounded-lg border border-ink-700 bg-ink-900/60 p-3 text-left transition-colors hover:border-accent/50 disabled:opacity-40">
                <Play className="mt-0.5 h-4 w-4 shrink-0 text-accent-soft" />
                <span><span className="block text-sm font-medium capitalize text-zinc-200">{s.id} investigation</span><span className="mt-0.5 block text-xs text-zinc-500">{s.question}</span></span>
              </button>
            ))}
          </div>
        </Panel>
        <Panel title="Ask the agent">
          {ai ? (
            <>
              <Chip tone="accent"><Bot className="h-3 w-3" />AI planning enabled ({status?.ai_provider})</Chip>
              <textarea aria-label="Investigation question" value={q} onChange={(e) => setQ(e.target.value)} maxLength={1000} rows={4} placeholder="e.g. Which markets are driving the revenue decline in 2011?"
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(); }}
                className="mt-3 w-full resize-none rounded-lg border border-ink-600 bg-ink-900 p-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-accent focus:outline-none" />
              <div className="mt-2 flex items-center gap-2">
                <button className="btn btn-primary" disabled={!q.trim() || busy || !ready} onClick={submit}><Send className="h-4 w-4" />{followUp ? "Ask follow-up" : "Investigate"}</button>
                {busy && <button className="btn" onClick={cancel}><Square className="h-4 w-4" />Stop</button>}
              </div>
              {!followUp && <div className="mt-3 space-y-1">{SUGGESTED.map((s) => <button key={s} onClick={() => setQ(s)} className="block w-full rounded px-2 py-1 text-left text-xs text-zinc-500 hover:bg-ink-800 hover:text-zinc-300">{s}</button>)}</div>}
              <p className="mt-3 text-[11px] leading-relaxed text-zinc-600">Your question and aggregated tool results (never raw transactions or customer identifiers) are sent to {status?.ai_provider}.</p>
            </>
          ) : (
            <div data-testid="no-ai">
              <Chip tone="muted"><Lock className="h-3 w-3" />Free-text investigations unavailable</Chip>
              <p className="mt-3 text-sm text-zinc-400">Free-form questions need an AI provider to plan the investigation. None is configured on the server, so OpsLens will not pretend to answer them.</p>
              <p className="mt-2 text-xs text-zinc-500">Set <code className="font-mono">ANTHROPIC_API_KEY</code> or <code className="font-mono">OPENAI_API_KEY</code> in the backend environment and restart it. Keys are never entered in the browser. The preset scenarios work now.</p>
              <div className="mt-3 flex items-center gap-2 text-xs text-warn"><TerminalSquare className="h-3.5 w-3.5" />Scripted mode: real calculations, no AI.</div>
            </div>
          )}
        </Panel>
      </div>

      <div className="mt-6 space-y-8">
        {runs.length === 0 && <p className="py-10 text-center text-sm text-zinc-600">No investigation yet. Pick a scenario to watch the agent work. Nothing is stored; refreshing the page clears everything.</p>}
        {runs.map((r) => <RunView key={r.id} run={r} />)}
        <div ref={end} />
      </div>
    </>
  );
}
