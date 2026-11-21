"use client";
import { AlertCircle, CheckCircle2, CircleDot, Loader2, XCircle } from "lucide-react";
import type { TimelineItem } from "@/lib/investigation";

const icon = (s: TimelineItem["status"]) =>
  s === "running" ? <Loader2 className="h-4 w-4 animate-spin text-accent-soft" aria-label="running" /> :
  s === "ok" ? <CheckCircle2 className="h-4 w-4 text-ok" aria-label="succeeded" /> :
  s === "failed" ? <XCircle className="h-4 w-4 text-bad" aria-label="failed" /> : <CircleDot className="h-4 w-4 text-zinc-500" aria-label="info" />;

/** Renders ONLY items produced by backend events (see applyEvent). The spinner shows solely between a real tool_started and its finish/failure event. */
export function Timeline({ items, startedAt }: { items: TimelineItem[]; startedAt?: number }) {
  if (!items.length) return <p className="flex items-center gap-2 text-sm text-zinc-500"><AlertCircle className="h-4 w-4" />Waiting for the first backend event…</p>;
  return (
    <ol aria-label="Execution timeline" className="relative space-y-0">
      {items.map((it, i) => (
        <li key={it.key} data-status={it.status} data-kind={it.kind} className="relative flex gap-3 pb-4 last:pb-0">
          {i < items.length - 1 && <span className="absolute left-[7px] top-5 h-full w-px bg-ink-600" aria-hidden />}
          <span className="relative z-10 mt-0.5 grid h-4 w-4 place-items-center rounded-full bg-ink-850">{icon(it.status)}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className={`text-sm ${it.status === "failed" ? "text-bad" : "text-zinc-200"}`}>{it.label}</span>
              {startedAt !== undefined && <span className="font-mono text-[11px] tabular-nums text-zinc-600">+{Math.max(0, Math.round((it.ts - startedAt) * 1000))} ms</span>}
            </div>
            {it.detail && <p className={`mt-0.5 break-words text-xs ${it.status === "failed" ? "text-bad/80" : "text-zinc-500"}`}>{it.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
