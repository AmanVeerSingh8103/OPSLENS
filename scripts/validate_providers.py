"""Live provider validation. Reads keys from the environment ONLY (never paste keys into chat or commit them).

    export ANTHROPIC_API_KEY=...   # and/or OPENAI_API_KEY=...
    python scripts/validate_providers.py
Runs a real multi-tool investigation + follow-up against the prepared dataset for each configured provider and
reports exactly what was and was not exercised. Providers without a key are reported as SKIPPED (not passed).
"""
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from opslens.agent import run_investigation
from opslens.config import get_settings
from opslens.engine import Engine
from opslens.providers import AnthropicProvider, OpenAIProvider, ProviderError
from opslens.sessions import SessionStore

s = get_settings(); bad = False
if not s.parquet.exists():
    print("Prepare the dataset first: python -m opslens.ingest --download\nRESULT: NOT VALIDATED"); sys.exit(2)
e = Engine(s.parquet)

async def go(p, q, hist=None):
    return [ev async for ev in run_investigation(engine=e, provider=p, question=q, history=hist or [])]

for name, key, cls, model in (("anthropic", s.anthropic_key, AnthropicProvider, s.anthropic_model), ("openai", s.openai_key, OpenAIProvider, s.openai_model)):
    if not key:
        print(f"SKIPPED {name}: no key in environment"); continue
    p = cls(key, model); print(f"== {name} model={model}")
    try:
        evs = asyncio.run(go(p, "Investigate the revenue trend, find months with significant declines and check for unusual activity."))
    except ProviderError as ex:
        print("FAIL auth/provider:", ex); bad = True; continue
    t = [x["type"] for x in evs]
    tools = [x["tool"] for x in evs if x["type"] == "tool_finished"]
    rep = next((x["report"] for x in evs if x["type"] == "report"), None)
    print("events:", t); print("tools executed:", tools)
    print("multi-tool:", "PASS" if len(tools) >= 2 else "FAIL"); bad |= len(tools) < 2
    print("report generated_by:", rep and rep["generated_by"], "(ai = passed numeric validation; deterministic = model output rejected)")
    print("validation attempts:", [(x["ok"], x.get("unsupported_numbers")) for x in evs if x["type"] == "validation_result"])
    if rep:
        st = SessionStore(); sid, _ = st.add_turn(None, "first", rep)
        evs2 = asyncio.run(go(p, "Which of those declines was largest, and what does the seasonal pattern suggest?", st.history(sid)))
        print("follow-up completed:", any(x["type"] == "report" for x in evs2))
print("\nDONE (SKIPPED providers were NOT tested)"); sys.exit(1 if bad else 0)
