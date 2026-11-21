export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface ToolResult {
  metrics: Record<string, string | number | null>;
  tables: Record<string, Record<string, string | number | boolean | null>[]>;
  notes: string[];
}
export interface ApiErrorBody { code: string; message: string }
export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, body: ApiErrorBody) { super(body.message); this.code = body.code; this.status = status; }
}

export interface Status {
  dataset_ready: boolean; dataset_message: string | null; ai_configured: boolean; ai_provider: string | null;
  privacy_notice: string; attribution: string; license: string; source: string;
}
export interface Scenario { id: string; question: string }

async function parseError(res: Response): Promise<ApiError> {
  try {
    const j = await res.json();
    const e = j.error ?? j.detail?.error ?? j.detail;
    if (e && typeof e === "object" && "code" in e) return new ApiError(res.status, e as ApiErrorBody);
    if (Array.isArray(j.detail)) return new ApiError(res.status, { code: "invalid_request", message: "The request was rejected as invalid." });
  } catch { /* fall through */ }
  return new ApiError(res.status, { code: "http_error", message: `Request failed (HTTP ${res.status}).` });
}

export async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try { res = await fetch(`${API_URL}${path}`, { cache: "no-store" }); }
  catch { throw new ApiError(0, { code: "backend_unreachable", message: `Cannot reach the OpsLens backend at ${API_URL}. Is it running?` }); }
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

const toolCache = new Map<string, Promise<{ result: ToolResult; duration_ms: number }>>();
export function runTool(name: string, args: Record<string, unknown> = {}) {
  const key = name + JSON.stringify(args);
  const hit = toolCache.get(key);
  if (hit) return hit;
  const p = (async () => {
    let res: Response;
    try { res = await fetch(`${API_URL}/api/tools/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(args) }); }
    catch { throw new ApiError(0, { code: "backend_unreachable", message: `Cannot reach the OpsLens backend at ${API_URL}. Is it running?` }); }
    if (!res.ok) throw await parseError(res);
    return res.json();
  })();
  p.catch(() => toolCache.delete(key));
  toolCache.set(key, p);
  return p;
}
export const clearToolCache = () => toolCache.clear();

// ---------------------------------------------------------------- SSE
export interface SseEvent { seq: number; ts: number; type: string; [k: string]: any }

/** Pure parser: returns complete events found in buffer plus the unconsumed remainder. */
export function parseSseChunk(buffer: string): { events: SseEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: SseEvent[] = [];
  for (const block of parts) {
    const data = block.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
    if (!data) continue;
    try { events.push(JSON.parse(data)); } catch { /* ignore malformed frame */ }
  }
  return { events, rest };
}

export interface InvestigateBody { question?: string; scenario?: string; session_id?: string }

export async function streamInvestigation(body: InvestigateBody, onEvent: (e: SseEvent) => void, signal?: AbortSignal): Promise<void> {
  let res: Response;
  try { res = await fetch(`${API_URL}/api/investigate`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal }); }
  catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError(0, { code: "backend_unreachable", message: `Cannot reach the OpsLens backend at ${API_URL}. Is it running?` });
  }
  if (!res.ok || !res.body) throw await parseError(res);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const { events, rest } = parseSseChunk(buf);
    buf = rest;
    events.forEach(onEvent);
  }
}

export const sessionExportUrl = (sid: string, turn: number, kind: "pdf" | "csv", extra = "") => `${API_URL}/api/sessions/${sid}/turns/${turn}/export.${kind}${extra}`;
export const toolCsvUrl = (tool: string, table: string) => `${API_URL}/api/export/tool/${tool}.csv?table=${encodeURIComponent(table)}`;
