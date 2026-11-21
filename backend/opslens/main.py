import json
import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .agent import SCENARIOS, run_investigation
from .config import get_settings
from .engine import DatasetNotReady, Engine
from .exports import metrics_csv, report_pdf, table_csv, tool_table_csv
from .sessions import SessionStore
from .providers import Provider, get_provider
from .tools import TOOLS, ToolError, execute_tool, tool_specs

log = logging.getLogger("opslens")  # only method/path/status are ever logged: never prompts, questions, keys or data

PRIVACY_NOTICE = ("Raw data is processed locally on this server. When you run an AI investigation, your question and the aggregated "
                  "tool results (totals, monthly figures, top-N tables; never raw transactions or customer/invoice identifiers) "
                  "are sent to the configured AI provider. Preset scenarios run without any AI provider.")
ATTRIBUTION = "Online Retail II, UCI Machine Learning Repository. Daqing Chen. DOI 10.24432/C5CG6D. CC BY 4.0."


class InvestigateBody(BaseModel):
    """Clients may NOT send history or evidence: follow-up context lives server-side, keyed by session_id."""
    model_config = ConfigDict(extra="forbid")
    question: str = Field("", max_length=1000)
    scenario: str | None = Field(None, max_length=40)
    session_id: str | None = Field(None, max_length=64)


class Limiter:
    def __init__(self, per_min: int):
        self.per_min, self.hits = per_min, defaultdict(deque)

    def check(self, key: str):
        now, q = time.time(), self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_min:
            raise HTTPException(429, {"code": "rate_limited", "message": "Too many requests. Please wait a minute."})
        q.append(now)


def create_app(engine: Engine | None = None, provider: Provider | None = None, use_env_provider: bool = True, sessions: SessionStore | None = None) -> FastAPI:
    s = get_settings()
    app = FastAPI(title="OpsLens API", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["GET", "POST"], allow_headers=["content-type"])
    limiter = Limiter(s.rate_limit_per_min)
    store = sessions or SessionStore()
    state = {"engine": engine, "provider": provider if provider or not use_env_provider else get_provider(s)}

    def eng() -> Engine:
        if state["engine"] is None:
            state["engine"] = Engine(s.parquet)  # raises DatasetNotReady
        return state["engine"]

    @app.exception_handler(DatasetNotReady)
    async def _nr(_, ex):
        return JSONResponse(status_code=503, content={"error": {"code": "dataset_not_ready", "message": str(ex)}})

    @app.exception_handler(HTTPException)
    async def _http(_, ex):
        d = ex.detail if isinstance(ex.detail, dict) else {"code": "http_error", "message": str(ex.detail)}
        return JSONResponse(status_code=ex.status_code, content={"error": d})

    @app.middleware("http")
    async def _log(request: Request, call_next):
        resp = await call_next(request)
        log.info("%s %s %s", request.method, request.url.path, resp.status_code)
        return resp

    @app.get("/api/status")
    def status():
        try:
            e = eng(); ready, msg = True, None
        except DatasetNotReady as ex:
            ready, msg = False, str(ex)
        p = state["provider"]
        return {"dataset_ready": ready, "dataset_message": msg, "ai_configured": p is not None, "ai_provider": p.name if p else None,
                "privacy_notice": PRIVACY_NOTICE, "attribution": ATTRIBUTION, "license": "CC BY 4.0",
                "source": "https://archive.ics.uci.edu/dataset/502/online+retail+ii"}

    @app.get("/api/tools")
    def tools():
        return {"tools": tool_specs()}

    @app.get("/api/scenarios")
    def scenarios():
        return {"scenarios": [{"id": k, "question": v[0]} for k, v in SCENARIOS.items()]}

    @app.post("/api/tools/{name}")
    def run_tool(name: str, request: Request, args: dict | None = None):
        limiter.check(request.client.host if request.client else "x")
        if name not in TOOLS:
            raise HTTPException(404, {"code": "unknown_tool", "message": "Unknown tool."})
        e = eng()
        t0 = time.perf_counter()
        try:
            res = execute_tool(e, name, args or {})
        except ToolError as ex:
            raise HTTPException(422, {"code": "invalid_tool_call", "message": str(ex)})
        return {"tool": name, "duration_ms": round((time.perf_counter() - t0) * 1000, 1), "result": res}

    @app.get("/api/explorer/preview")
    def preview(page: int = 1, page_size: int = 25):
        if page < 1 or not 1 <= page_size <= 100:
            raise HTTPException(422, {"code": "bad_pagination", "message": "page >= 1 and 1 <= page_size <= 100"})
        e = eng()
        df = e.df("SELECT stock_code, description, quantity, invoice_date, unit_price, country, is_cancellation, is_sale, line_value FROM tx ORDER BY invoice_date, stock_code LIMIT ? OFFSET ?", [page_size, (page - 1) * page_size])
        total = int(e.df("SELECT COUNT(*) AS n FROM tx")["n"].iloc[0])
        return {"page": page, "page_size": page_size, "total_rows": total, "rows": json.loads(df.to_json(orient="records", date_format="iso")),
                "note": "Invoice numbers and customer identifiers are intentionally not exposed."}

    @app.post("/api/investigate")
    async def investigate(body: InvestigateBody, request: Request):
        limiter.check(request.client.host if request.client else "x")
        if not body.question.strip() and body.scenario not in SCENARIOS:
            raise HTTPException(422, {"code": "empty_question", "message": "Provide a question or a valid scenario id."})
        e = eng()
        if body.session_id and not store.exists(body.session_id):
            raise HTTPException(410, {"code": "session_expired", "message": "Investigation context expired or is unknown. Start a new investigation."})
        q = body.question.strip() or SCENARIOS[body.scenario][0]
        history = store.history(body.session_id)

        async def stream():
            async for event in run_investigation(engine=e, provider=state["provider"], question=q, history=history, scenario=body.scenario):
                if event["type"] == "report":  # context is created here, by the server, from the validated report only
                    sid, turn = store.add_turn(body.session_id, q, event["report"])
                    event = {**event, "session_id": sid, "turn": turn}
                yield f"data: {json.dumps(event, default=str)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def _turn(sid: str, n: int, request: Request) -> dict:
        limiter.check(request.client.host if request.client else "x")
        t = store.report(sid, n)
        if t is None:
            raise HTTPException(404, {"code": "report_not_found", "message": "Report not found or session expired."})
        return t

    @app.get("/api/sessions/{sid}/turns/{n}/export.pdf")
    def export_pdf(sid: str, n: int, request: Request):
        t = _turn(sid, n, request)
        return Response(report_pdf(t["report"], t["question"]), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="opslens-report.pdf"'})

    @app.get("/api/sessions/{sid}/turns/{n}/export.csv")
    def export_csv(sid: str, n: int, request: Request, evidence: str | None = None, table: str | None = None):
        t = _turn(sid, n, request)
        if evidence and table:
            data = table_csv(t["report"], evidence, table)
            if data is None:
                raise HTTPException(404, {"code": "table_not_found", "message": "No such evidence table."})
            name = f"opslens-{evidence}-{table}.csv"
        else:
            data, name = metrics_csv(t["report"]), "opslens-metrics.csv"
        return Response(data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/export/tool/{name}.csv")
    def export_tool_csv(name: str, table: str, request: Request):
        limiter.check(request.client.host if request.client else "x")
        if name not in TOOLS:
            raise HTTPException(404, {"code": "unknown_tool", "message": "Unknown tool."})
        try:
            res = execute_tool(eng(), name, {})
        except ToolError as ex:
            raise HTTPException(422, {"code": "invalid_tool_call", "message": str(ex)})
        data = tool_table_csv(res, table)
        if data is None:
            raise HTTPException(404, {"code": "table_not_found", "message": "No such table for this tool."})
        return Response(data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="opslens-{name}-{table}.csv"'})

    return app


def _default_app():
    return create_app()


app = _default_app()
