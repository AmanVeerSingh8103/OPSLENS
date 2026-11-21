"use client";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/Shell";
import { ReportView } from "@/components/RunView";
import { Chip, Panel } from "@/components/ui";
import { useApp } from "@/lib/store";

export default function Reports() {
  const { runs } = useApp();
  const withReport = runs.filter((r) => r.report);
  const [sel, setSel] = useState<string | null>(null);
  const cur = withReport.find((r) => r.id === sel) ?? withReport[withReport.length - 1];
  return (
    <>
      <PageHeader title="Reports" sub="Reports from this browser session. They live in memory only: refresh the page and they are gone, so export the ones you want to keep." />
      {withReport.length === 0 ? (
        <Panel><p className="text-sm text-zinc-400">No reports yet. <Link className="text-accent-soft underline" href="/investigations">Run an investigation</Link> to generate one, then export it as PDF or CSV here.</p></Panel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-4">
          <div className="space-y-2 lg:col-span-1" role="list">
            {withReport.map((r) => (
              <button key={r.id} role="listitem" onClick={() => setSel(r.id)} className={`w-full rounded-lg border p-3 text-left text-sm ${cur?.id === r.id ? "border-accent/60 bg-accent/10" : "border-ink-700 bg-ink-850 hover:border-ink-600"}`}>
                <div className="line-clamp-2 text-zinc-200">{r.question}</div>
                <div className="mt-1.5"><Chip tone={r.report!.generated_by === "ai" ? "accent" : "warn"}>{r.report!.generated_by === "ai" ? "AI-interpreted" : "Scripted"}</Chip></div>
              </button>
            ))}
          </div>
          <div className="lg:col-span-3">{cur && <ReportView run={cur} />}</div>
        </div>
      )}
    </>
  );
}
