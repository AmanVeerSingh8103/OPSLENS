"""Run on a machine WITH the real UCI workbook. Prints PASS/FAIL per check; exit code 1 on any FAIL.

    python -m opslens.ingest --download        # or place online_retail_II.xlsx in data/raw/
    python scripts/validate_real_dataset.py
Nothing here is asserted from memory except structural invariants; documented UCI facts are reported as WARN if they differ.
"""
import sys, json
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from opslens.config import get_settings
from opslens.engine import Engine
from opslens.ingest import read_workbook, clean
from opslens.tools import TOOLS, execute_tool

s = get_settings(); fails = []
def check(name, ok, detail=""):
    print(("PASS" if ok else "FAIL"), name, detail); (not ok) and fails.append(name)
def warn(name, ok, detail=""):
    print(("PASS" if ok else "WARN"), name, detail)

xlsx = next(iter((s.data_dir / "raw").glob("*.xlsx")), None)
check("raw workbook present", xlsx is not None, str(xlsx))
if xlsx is None:
    print("\nCannot validate: no workbook in data/raw/. Run `python -m opslens.ingest --download` or place online_retail_II.xlsx there.\nRESULT: NOT VALIDATED"); sys.exit(2)
sheets = pd.read_excel(xlsx, sheet_name=None, dtype={"Invoice": str, "StockCode": str})
check("workbook has 2 sheets", len(sheets) == 2, str(list(sheets)))
raw = pd.concat(sheets.values(), ignore_index=True)
warn("raw rows ~ 1,067,371", abs(len(raw) - 1_067_371) < 5000, str(len(raw)))
df, rep = clean(raw)
print(json.dumps(rep, indent=2))
check("no customer id in processed data", "customer_id" not in df.columns)
check("dates parsed", df.invoice_date.notna().all() and df.invoice_date.dtype.kind == "M")
warn("date range 2009-12-01..2011-12-09", str(df.invoice_date.min().date()) == "2009-12-01" and str(df.invoice_date.max().date()) == "2011-12-09", f"{df.invoice_date.min()} .. {df.invoice_date.max()}")
check("no duplicates remain", not df.duplicated().any())
check("cancellations never counted as sales", df[df.is_cancellation].is_sale.sum() == 0)
check("sales have positive qty and price", ((df[df.is_sale].quantity > 0) & (df[df.is_sale].unit_price > 0)).all())
check("negative-quantity non-cancellations are not sales", df[(~df.is_cancellation) & (df.quantity < 0)].is_sale.sum() == 0)
check("no negative prices remain", (df.unit_price >= 0).all())
if not s.parquet.exists():
    print("Run `python -m opslens.ingest` first so the Parquet file exists.\nRESULT: NOT VALIDATED"); sys.exit(2)
e = Engine(s.parquet)
ov = execute_tool(e, "get_dataset_overview", {})["metrics"]
sale = df[df.is_sale]
check("DuckDB revenue == pandas revenue", abs(ov["sales_revenue"] - float((sale.quantity * sale.unit_price).sum())) < 0.05, str(ov))
check("DuckDB invoice counts == pandas", ov["completed_invoices"] == sale.invoice.nunique() and ov["cancellation_invoices"] == df[df.is_cancellation].invoice.nunique())
check("parquet row count == cleaned rows", ov["total_records"] == len(df) == rep["rows_clean"])
args = {"get_period_comparison": dict(a_start="2010-01", a_end="2010-03", b_start="2011-01", b_end="2011-03")}
for name in TOOLS:
    try: execute_tool(e, name, args.get(name, {})); check(f"tool {name}", True)
    except Exception as ex: check(f"tool {name}", False, repr(ex))
print("\nRESULT:", "FAILED " + str(fails) if fails else "ALL CHECKS PASSED"); sys.exit(1 if fails else 0)
