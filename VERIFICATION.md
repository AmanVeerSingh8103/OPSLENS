# Verification status (what was actually run)

Environment: sandbox without access to archive.ics.uci.edu and without any AI provider keys.

## Verified (executed, passing)
| Area | Evidence |
|---|---|
| Backend | 72 pytest tests pass: ingestion/cleaning rules, revenue/invoice/period/cancellation calculations vs independent pandas, all 16 tools, tool-registry security (unknown tools, injection, extra args), agent loop (multi-tool, failures, clarification, unsupported, malformed output, provider errors), numeric evidence validation, privacy (LLM payloads, log contents), follow-up security, session expiry/bounds/isolation, all 7 scenarios, PDF + CSV exports, provider HTTP layer |
| Frontend | `tsc --noEmit` clean; `next lint` clean; 29 vitest tests pass (SSE parser, reducer, pages vs mocked backend, honest error states, static rule guards); `next build` succeeds (all 8 routes) |
| Full stack over real HTTP (uvicorn + `next start`) | SSE stream with 6 real tool executions and measured durations; PDF (valid `%PDF`) and CSV download; forged `history` → 422; forged session → 410; free text without a provider → `provider_not_configured`; CORS preflight; all 7 pages return 200; question text absent from server log; no secret values in the built bundle (the only string match is the setup instruction text `ANTHROPIC_API_KEY=...`) |

## NOT verified
| Area | Why | How to verify |
|---|---|---|
| **Real UCI dataset** (sheet handling, real missing/duplicate/cancellation counts, real revenue, DuckDB on ~1M rows) | Sandbox cannot resolve archive.ics.uci.edu. All data tests and the HTTP run used a small synthetic fixture generated inside the test suite / a /tmp QA copy (never shipped, never read by the app). The xlsx→parquet path was smoke-tested only on a workbook I generated in the UCI two-sheet layout. | `python -m opslens.ingest --download` then `python scripts/validate_real_dataset.py` |
| **Live Anthropic / OpenAI** (auth, model names, real plan/report quality, real numeric-check pass rate, real follow-ups) | No API keys in the environment. Only mocked HTTP transports (request shape, retries, 401/429/5xx, timeouts, malformed shapes) and a fake provider were used. Default model names (`claude-sonnet-5-5`, `gpt-4o`) are unconfirmed; override with env vars. | export keys in your shell, `python scripts/validate_providers.py` |
| **Visual/responsive layout** | No browser available. Layout is Tailwind-responsive by construction (collapsible desktop sidebar, off-canvas mobile nav, responsive grids, scrolling tables) but was not screenshot-tested at any viewport. | Open at 375/768/1280 px |
| Real-browser SSE rendering | SSE verified with curl and in jsdom with chunked mocked streams, not in a real browser. | Run an investigation in the UI |
| Provider-native tool calling | Not implemented: tool choice is a validated JSON plan. | n/a |
