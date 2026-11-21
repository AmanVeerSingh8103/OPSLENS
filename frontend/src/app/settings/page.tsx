"use client";
import { PageHeader } from "@/components/Shell";
import { Chip, ErrorState, Panel } from "@/components/ui";
import { API_URL } from "@/lib/api";
import { useApp } from "@/lib/store";

export default function SettingsPage() {
  const { status, statusError } = useApp();
  return (
    <>
      <PageHeader title="Settings" sub="Provider status and privacy. Configuration lives on the server; the browser never handles API keys." />
      {statusError && <ErrorState error={statusError} />}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="AI provider">
          {!status ? <p className="text-sm text-zinc-500">Checking…</p> : status.ai_configured ? (
            <><Chip tone="accent">Configured: {status.ai_provider}</Chip><p className="mt-3 text-sm text-zinc-400">Free-text investigations use the real agent. Configured status means a key is present; it does not prove the key is valid until a request succeeds.</p></>
          ) : (
            <><Chip tone="muted">Not configured</Chip><p className="mt-3 text-sm text-zinc-400">Dashboards, Data Explorer, Insights and the seven preset scenarios work without a provider. To enable free-text investigations, set one of these in the backend environment and restart it:</p>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-ink-900 p-3 text-xs text-zinc-300">{`ANTHROPIC_API_KEY=...   # or\nOPENAI_API_KEY=...\nAI_PROVIDER=anthropic   # optional: anthropic | openai`}</pre></>
          )}
        </Panel>
        <Panel title="Backend connection"><dl className="space-y-1 text-sm"><div className="flex justify-between"><dt className="text-zinc-500">API URL</dt><dd className="font-mono text-zinc-300">{API_URL}</dd></div>
          <div className="flex justify-between"><dt className="text-zinc-500">Dataset</dt><dd>{status ? (status.dataset_ready ? "Ready" : "Not prepared") : "…"}</dd></div></dl></Panel>
        <Panel title="Privacy" className="lg:col-span-2">
          <p className="text-sm text-zinc-300">{status?.privacy_notice}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-zinc-500"><li>No accounts, cookies, local storage or conversation database. Investigations live in server memory (up to 1 hour) and browser memory only.</li>
            <li>Questions and prompts are not written to server logs.</li><li>The AI provider you configure has its own data-handling terms.</li></ul>
        </Panel>
      </div>
    </>
  );
}
