import { vi } from "vitest";

export const enc = (s: string) => new TextEncoder().encode(s);
export const frame = (o: object) => `data: ${JSON.stringify(o)}\n\n`;
export function sseResponse(frames: string[], chunkSize = 0): Response {
  const text = frames.join("");
  const chunks = chunkSize ? text.match(new RegExp(`[\\s\\S]{1,${chunkSize}}`, "g"))! : [text];
  return new Response(new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(enc(x))); c.close(); } }), { status: 200, headers: { "content-type": "text/event-stream" } });
}
export const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;
export function mockFetch(routes: Record<string, Handler>) {
  const f = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const key = Object.keys(routes).find((k) => url.includes(k));
    if (!key) return json({ error: { code: "not_mocked", message: url } }, 500);
    return routes[key](url, init);
  });
  vi.stubGlobal("fetch", f);
  return f;
}
export const STATUS = (o: Partial<{ ai: boolean; ready: boolean }> = {}) => ({
  dataset_ready: o.ready ?? true, dataset_message: o.ready === false ? "Processed dataset not found." : null, ai_configured: o.ai ?? false, ai_provider: o.ai ? "anthropic" : null,
  privacy_notice: "Raw data is processed locally on this server. ... sent to the configured AI provider.", attribution: "Online Retail II ... CC BY 4.0.", license: "CC BY 4.0", source: "https://archive.ics.uci.edu/dataset/502/online+retail+ii",
});
export const SCENARIOS = { scenarios: [{ id: "revenue", question: "Investigate the revenue trend and identify periods of significant decline." }, { id: "executive", question: "Prepare an executive business performance report using the available dataset." }] };
