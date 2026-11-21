import { readdirSync, readFileSync, statSync } from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

const SRC = path.resolve(__dirname, "..");
const files = (d: string): string[] => readdirSync(d).flatMap((n) => { const p = path.join(d, n); return statSync(p).isDirectory() ? (n === "__tests__" ? [] : files(p)) : /\.(tsx?|css)$/.test(n) ? [p] : []; });
const strip = (t: string) => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1"); // guards check code, not comments
const src = files(SRC).map((f) => ({ f: path.relative(SRC, f), t: strip(readFileSync(f, "utf8")) }));

describe("static guards for the engineering rules", () => {
  it("Rule 1: no hardcoded currency or KPI numbers in UI source", () => {
    for (const { f, t } of src) expect(t, f).not.toMatch(/£\s?\d/);
    for (const { f, t } of src.filter((s) => /app\/|components\//.test(s.f))) expect(t, f).not.toMatch(/(revenue|invoices|records)\s*[:=]\s*\d{3,}/i);
  });
  it("Rule 3 / privacy: no secrets, storage APIs, or cookies in frontend source", () => {
    for (const { f, t } of src) {
      expect(t, f).not.toMatch(/sk-ant-|sk-proj-|process\.env\.(ANTHROPIC|OPENAI)|(ANTHROPIC|OPENAI)_API_KEY\s*[:=]\s*['"`]\w/);
      expect(t, f).not.toMatch(/localStorage|sessionStorage|document\.cookie|indexedDB/);
      expect(t, f).not.toMatch(/NEXT_PUBLIC_[A-Z_]*(KEY|SECRET|TOKEN)/);
    }
  });
  it("Rule 5: no timers drive the execution timeline (no setTimeout/setInterval in agent UI code)", () => {
    for (const { f, t } of src.filter((s) => /investigation|store|Timeline|RunView|api\.ts/.test(s.f))) expect(t, f).not.toMatch(/setTimeout|setInterval/);
  });
  it("browser never sends history or evidence to the investigate endpoint", () => {
    const api = src.find((s) => s.f.endsWith("lib/api.ts"))!.t;
    expect(api).toMatch(/interface InvestigateBody \{ question\?: string; scenario\?: string; session_id\?: string \}/);
  });
});
