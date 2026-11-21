"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ApiError, getJson, streamInvestigation, type Scenario, type Status } from "./api";
import { applyEvent, failRun, newRun, type Run } from "./investigation";

interface Ctx {
  status: Status | null; statusError: string | null; scenarios: Scenario[]; runs: Run[]; sessionId: string | null; busy: boolean;
  start: (o: { question?: string; scenario?: string }) => Promise<void>; reset: () => void; cancel: () => void;
}
const C = createContext<Ctx | null>(null);

type Act = { t: "add"; run: Run } | { t: "ev"; id: string; ev: Parameters<typeof applyEvent>[1] } | { t: "fail"; id: string; code: string; message: string } | { t: "clear" };
function reducer(s: Run[], a: Act): Run[] {
  switch (a.t) {
    case "add": return [...s, a.run];
    case "ev": return s.map((r) => (r.id === a.id ? applyEvent(r, a.ev) : r));
    case "fail": return s.map((r) => (r.id === a.id ? failRun(r, a.code, a.message) : r));
    case "clear": return [];
  }
}

/** In-memory only: no localStorage/cookies. Refreshing the page clears all investigations. */
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [runs, dispatch] = useReducer(reducer, []);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const counter = useRef(0);

  useEffect(() => {
    getJson<Status>("/api/status").then(setStatus).catch((e: Error) => setStatusError(e.message));
    getJson<{ scenarios: Scenario[] }>("/api/scenarios").then((d) => setScenarios(d.scenarios)).catch(() => undefined);
  }, []);

  const start = useCallback(async ({ question, scenario }: { question?: string; scenario?: string }) => {
    const id = `run-${++counter.current}`;
    const q = question?.trim() || scenarios.find((s) => s.id === scenario)?.question || scenario || "";
    dispatch({ t: "add", run: newRun(id, q, scenario) });
    setBusy(true);
    abort.current = new AbortController();
    try {
      await streamInvestigation({ question: question?.trim() || undefined, scenario, session_id: sessionId ?? undefined }, (ev) => {
        dispatch({ t: "ev", id, ev });
        if (ev.type === "report" && ev.session_id) setSessionId(ev.session_id);
      }, abort.current.signal);
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "session_expired") setSessionId(null);
      dispatch({ t: "fail", id, code: err.code ?? "error", message: err.message ?? "Unexpected error" });
    } finally { setBusy(false); }
  }, [scenarios, sessionId]);

  const reset = useCallback(() => { abort.current?.abort(); dispatch({ t: "clear" }); setSessionId(null); setBusy(false); }, []);
  const cancel = useCallback(() => { abort.current?.abort(); setBusy(false); }, []);
  const v = useMemo(() => ({ status, statusError, scenarios, runs, sessionId, busy, start, reset, cancel }), [status, statusError, scenarios, runs, sessionId, busy, start, reset, cancel]);
  return <C.Provider value={v}>{children}</C.Provider>;
}
export function useApp() {
  const c = useContext(C);
  if (!c) throw new Error("useApp must be used inside AppProvider");
  return c;
}
