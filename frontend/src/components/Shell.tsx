"use client";
import { BarChart3, Bot, Database, FileText, Gauge, Info, Lightbulb, Menu, PanelLeftClose, PanelLeftOpen, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useApp } from "@/lib/store";
import { Chip } from "./ui";

const NAV = [
  { href: "/", label: "Overview", icon: Gauge }, { href: "/investigations", label: "Investigations", icon: Bot }, { href: "/data", label: "Data Explorer", icon: Database },
  { href: "/insights", label: "Insights", icon: Lightbulb }, { href: "/reports", label: "Reports", icon: FileText }, { href: "/about", label: "About Dataset", icon: Info }, { href: "/settings", label: "Settings", icon: Settings },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [open, setOpen] = useState(false);
  const { status, statusError } = useApp();
  const nav = (
    <nav aria-label="Primary" className="flex flex-col gap-1 p-2">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link key={href} href={href} onClick={() => setOpen(false)} title={label} aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${active ? "bg-accent/15 text-white ring-1 ring-accent/30" : "text-zinc-400 hover:bg-ink-800 hover:text-zinc-100"}`}>
            <Icon className="h-4 w-4 shrink-0" />{!collapsed && <span>{label}</span>}
          </Link>
        );
      })}
    </nav>
  );
  const brand = (
    <div className="flex h-14 items-center gap-2 border-b border-ink-700 px-4">
      <div className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-accent to-accent-blue"><BarChart3 className="h-4 w-4 text-white" /></div>
      {!collapsed && <div className="font-semibold tracking-tight">OpsLens</div>}
    </div>
  );
  return (
    <div className="flex min-h-screen">
      <aside className={`sticky top-0 hidden h-screen shrink-0 flex-col border-r border-ink-700 bg-ink-900 md:flex ${collapsed ? "w-16" : "w-60"} transition-[width]`}>
        {brand}{nav}
        <button className="mt-auto m-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-zinc-500 hover:bg-ink-800" onClick={() => setCollapsed((c) => !c)} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" />Collapse</>}
        </button>
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 border-r border-ink-700 bg-ink-900">{brand}{nav}</aside>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-ink-700 bg-ink-950/80 px-4 backdrop-blur">
          <button className="btn !p-2 md:hidden" onClick={() => setOpen((o) => !o)} aria-label="Toggle navigation">{open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}</button>
          <p className="hidden text-sm text-zinc-500 sm:block">Don&apos;t just show me the numbers. Tell me what&apos;s going wrong.</p>
          <div className="ml-auto flex items-center gap-2">
            {statusError ? <Chip tone="bad">Backend offline</Chip> : !status ? <Chip>Connecting…</Chip> : (
              <>
                <Chip tone={status.dataset_ready ? "ok" : "warn"}>{status.dataset_ready ? "Dataset ready" : "Dataset not prepared"}</Chip>
                <Chip tone={status.ai_configured ? "accent" : "muted"}>{status.ai_configured ? `AI: ${status.ai_provider}` : "AI: not configured"}</Chip>
              </>
            )}
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] p-4 sm:p-6">{children}</main>
        <footer className="border-t border-ink-700 px-6 py-4 text-xs text-zinc-600">Data: Online Retail II (UCI), Daqing Chen, DOI 10.24432/C5CG6D, CC BY 4.0. Historical data, not live. Revenue is not profit.</footer>
      </div>
    </div>
  );
}
export const PageHeader = ({ title, sub, right }: { title: string; sub?: string; right?: React.ReactNode }) => (
  <div className="mb-6 flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-xl font-semibold tracking-tight text-zinc-50 sm:text-2xl">{title}</h1>{sub && <p className="mt-1 max-w-3xl text-sm text-zinc-500">{sub}</p>}</div>{right}</div>
);
