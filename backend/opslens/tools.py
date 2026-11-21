"""Controlled analytical tool registry (Rule 2 + Rule 4).

Every tool: pydantic-validated args, parameterised SQL over the fixed `tx` view,
aggregated output only, hard row caps. No tool accepts SQL, code or column names.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .engine import Engine

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
MAX_ROWS = 40


class ToolError(Exception):
    pass


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filters(Strict):
    start_month: Optional[str] = Field(None, pattern=MONTH, description="YYYY-MM inclusive")
    end_month: Optional[str] = Field(None, pattern=MONTH, description="YYYY-MM inclusive")
    country: Optional[str] = Field(None, max_length=60, description="Exact country name from the dataset")


class TopN(Filters):
    top_n: int = Field(10, ge=1, le=25)


class NoArgs(Strict):
    pass


def _where(f: Filters, extra: str | None = None, e: Engine | None = None):
    cl, p = [], []
    if f.country is not None:
        if e is not None and f.country not in e.countries:
            raise ToolError(f"Unknown country '{f.country[:40]}'. Use get_country_performance to list valid values.")
        cl.append("country = ?"); p.append(f.country)
    if f.start_month:
        cl.append("year_month >= ?"); p.append(f.start_month)
    if f.end_month:
        cl.append("year_month <= ?"); p.append(f.end_month)
    if extra:
        cl.append(extra)
    return (" WHERE " + " AND ".join(cl)) if cl else "", p


def _rows(df: pd.DataFrame, nd: int = 2, cap: int = MAX_ROWS) -> list[dict]:
    return json.loads(df.head(cap).round(nd).to_json(orient="records", date_format="iso"))


def _num(x, nd: int = 2):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def _pct(a, b):
    return None if not b else round((a - b) / abs(b) * 100, 2)


def _out(metrics: dict, tables: dict | None = None, notes: list[str] | None = None) -> dict:
    return {"metrics": metrics, "tables": tables or {}, "notes": notes or []}


def _partial_note(e: Engine) -> list[str]:
    return [f"{e.partial_month} is a partial month (data ends {e.last_date.date()}) and is excluded from trend-decline logic."] if e.partial_month else []


# ---------------------------------------------------------------- tools
def get_dataset_overview(e: Engine, a: NoArgs):
    r = e.df("""SELECT COUNT(*) AS total_records,
        COUNT(DISTINCT CASE WHEN is_sale THEN invoice END) AS completed_invoices,
        COUNT(DISTINCT CASE WHEN is_cancellation THEN invoice END) AS cancellation_invoices,
        SUM(CASE WHEN is_sale THEN line_value END) AS sales_revenue,
        COUNT(DISTINCT CASE WHEN is_product THEN stock_code END) AS unique_products,
        COUNT(DISTINCT country) AS countries, MIN(invoice_date) AS first_date, MAX(invoice_date) AS last_date FROM tx""").iloc[0]
    inv = int(r.completed_invoices)
    return _out({
        "total_records": int(r.total_records), "completed_invoices": inv,
        "cancellation_invoices": int(r.cancellation_invoices), "sales_revenue": _num(r.sales_revenue),
        "unique_products": int(r.unique_products), "countries": int(r.countries),
        "average_invoice_value": _num(r.sales_revenue / inv) if inv else None,
        "first_date": str(r.first_date.date()), "last_date": str(r.last_date.date()),
    }, notes=["Revenue = Quantity x UnitPrice on sale lines (see data quality report). It is not profit."])


COLUMN_DOCS = {
    "invoice": "Invoice number; prefix 'C' = cancellation (never returned by tools)",
    "stock_code": "Product code (5-digit prefix = real product)", "description": "Product name",
    "quantity": "Units on the line (negative on cancellations/adjustments)", "invoice_date": "Invoice timestamp",
    "unit_price": "Unit price in GBP", "country": "Customer country", "is_cancellation": "Derived: invoice starts with 'C'",
    "is_product": "Derived: stock code looks like a product", "is_sale": "Derived: completed sale line",
    "line_value": "Derived: quantity x unit_price", "year_month": "Derived: YYYY-MM",
}


def get_dataset_schema(e: Engine, a: NoArgs):
    d = e.df("SELECT column_name, column_type FROM (DESCRIBE tx)")
    rows = [{"column": r.column_name, "type": r.column_type, "description": COLUMN_DOCS.get(r.column_name, "")} for r in d.itertuples()]
    return _out({"columns": len(rows)}, {"schema": rows}, ["CustomerID is removed during ingestion and is not available."])


def get_data_quality_report(e: Engine, a: NoArgs):
    live = e.df("""SELECT COUNT(*) AS rows, SUM(CASE WHEN description IS NULL THEN 1 ELSE 0 END) AS missing_description,
        SUM(CASE WHEN unit_price = 0 THEN 1 ELSE 0 END) AS zero_price_lines,
        SUM(CASE WHEN NOT is_product THEN 1 ELSE 0 END) AS non_product_lines FROM tx""").iloc[0]
    m = {k: int(v) for k, v in live.items()}
    m.update({k: v for k, v in e.ingest_report.items() if isinstance(v, int)})
    return _out(m, notes=["Cleaning rules: see ingest.py module docstring.", "Data is historical (Dec 2009 - Dec 2011), not live."])


def get_revenue_summary(e: Engine, a: Filters):
    w, p = _where(a, "is_sale", e)
    r = e.df(f"""SELECT SUM(line_value) AS revenue, COUNT(DISTINCT invoice) AS invoices, SUM(quantity) AS units,
        COUNT(DISTINCT stock_code) AS products, COUNT(DISTINCT country) AS countries FROM tx{w}""", p).iloc[0]
    inv = int(r.invoices)
    return _out({"revenue": _num(r.revenue), "invoices": inv, "units": _num(r.units, 0), "products": int(r.products),
                 "countries": int(r.countries), "average_invoice_value": _num(r.revenue / inv) if inv else None})


def get_revenue_trend(e: Engine, a: Filters, decline_threshold_pct: float = 10.0):
    w, p = _where(a, "is_sale", e)
    df = e.df(f"SELECT year_month, SUM(line_value) AS revenue, COUNT(DISTINCT invoice) AS invoices FROM tx{w} GROUP BY 1 ORDER BY 1", p)
    df["mom_change_pct"] = df["revenue"].pct_change() * 100
    df["is_partial"] = df["year_month"] == e.partial_month
    dec = df[(df.mom_change_pct <= -decline_threshold_pct) & ~df.is_partial]
    best = df.loc[df.revenue.idxmax()] if len(df) else None
    return _out({"months": len(df), "decline_threshold_pct": decline_threshold_pct, "significant_declines": len(dec),
                 "peak_month": None if best is None else best.year_month, "peak_revenue": None if best is None else _num(best.revenue)},
                {"monthly": _rows(df, cap=60), "significant_declines": _rows(dec)}, _partial_note(e))


class TrendArgs(Filters):
    decline_threshold_pct: float = Field(10.0, ge=1, le=90)


class PeriodArgs(Strict):
    a_start: str = Field(pattern=MONTH); a_end: str = Field(pattern=MONTH)
    b_start: str = Field(pattern=MONTH); b_end: str = Field(pattern=MONTH)
    country: Optional[str] = Field(None, max_length=60)


def get_period_comparison(e: Engine, a: PeriodArgs):
    def agg(s, en):
        w, p = _where(Filters(start_month=s, end_month=en, country=a.country), "is_sale", e)
        r = e.df(f"SELECT SUM(line_value) AS revenue, COUNT(DISTINCT invoice) AS invoices, SUM(quantity) AS units FROM tx{w}", p).iloc[0]
        rev = _num(r.revenue) or 0.0; inv = int(r.invoices)
        return {"revenue": rev, "invoices": inv, "units": _num(r.units, 0) or 0, "average_invoice_value": _num(rev / inv) if inv else None}
    A, B = agg(a.a_start, a.a_end), agg(a.b_start, a.b_end)
    return _out({"period_a_revenue": A["revenue"], "period_b_revenue": B["revenue"], "revenue_change_pct": _pct(B["revenue"], A["revenue"]),
                 "period_a_invoices": A["invoices"], "period_b_invoices": B["invoices"], "invoice_change_pct": _pct(B["invoices"], A["invoices"]),
                 "period_a_avg_invoice": A["average_invoice_value"], "period_b_avg_invoice": B["average_invoice_value"],
                 "avg_invoice_change_pct": _pct(B["average_invoice_value"] or 0, A["average_invoice_value"] or 0)},
                notes=["Period A is the baseline; changes are B relative to A. Periods of different length are not normalised."])


class ProductArgs(TopN):
    sort_by: Literal["revenue", "units"] = "revenue"


def get_product_performance(e: Engine, a: ProductArgs):
    w, p = _where(a, "is_sale", e)
    df = e.df(f"SELECT stock_code, MAX(description) AS description, SUM(line_value) AS revenue, SUM(quantity) AS units FROM tx{w} GROUP BY 1 ORDER BY {a.sort_by} DESC LIMIT {int(a.top_n)}", p)
    total = e.df(f"SELECT SUM(line_value) AS t FROM tx{w}", p)["t"].iloc[0]
    df["share_pct"] = df["revenue"] / total * 100
    tables = {"top_products": _rows(df)}
    notes = _partial_note(e)
    cm = e.complete_months
    metrics = {"top_n": len(df), "top_products_revenue_share_pct": _num(df["revenue"].sum() / total * 100) if total else None}
    if len(cm) >= 4:
        n = min(6, len(cm) // 2); recent, prior = cm[-n:], cm[-2 * n:-n]
        ph = lambda xs: ",".join("?" * len(xs))
        d2 = e.df(f"""SELECT stock_code, MAX(description) AS description,
            SUM(CASE WHEN year_month IN ({ph(recent)}) THEN line_value ELSE 0 END) AS recent_revenue,
            SUM(CASE WHEN year_month IN ({ph(prior)}) THEN line_value ELSE 0 END) AS prior_revenue
            FROM tx{w} GROUP BY 1""", recent + prior + p)
        d2 = d2[d2.prior_revenue >= 1000]
        d2["change_pct"] = (d2.recent_revenue - d2.prior_revenue) / d2.prior_revenue * 100
        dec = d2.sort_values("change_pct").head(int(a.top_n))
        tables["declining_products"] = _rows(dec)
        notes.append(f"Declining products compare last {n} complete months ({recent[0]}..{recent[-1]}) with the previous {n} ({prior[0]}..{prior[-1]}); only products with >= 1000 prior revenue.")
        metrics["decline_window_months"] = n
    return _out(metrics, tables, notes)


def get_country_performance(e: Engine, a: TopN):
    w, p = _where(a, "is_sale", e)
    df = e.df(f"SELECT country, SUM(line_value) AS revenue, COUNT(DISTINCT invoice) AS invoices FROM tx{w} GROUP BY 1 ORDER BY 2 DESC", p)
    total = df.revenue.sum()
    df["share_pct"] = df.revenue / total * 100 if total else 0
    df["average_invoice_value"] = df.revenue / df.invoices
    top = df.head(int(a.top_n))
    return _out({"countries": len(df), "top_country": None if df.empty else df.country.iloc[0],
                 "top_country_share_pct": None if df.empty else _num(df.share_pct.iloc[0]), "top_n_share_pct": _num(top.share_pct.sum())},
                {"countries": _rows(top)})


def get_cancellation_analysis(e: Engine, a: TopN):
    w, p = _where(a, None, e)
    m = e.df(f"""SELECT year_month,
        COUNT(DISTINCT CASE WHEN is_sale THEN invoice END) AS sale_invoices,
        COUNT(DISTINCT CASE WHEN is_cancellation THEN invoice END) AS cancellation_invoices,
        SUM(CASE WHEN is_sale THEN line_value ELSE 0 END) AS sales_value,
        SUM(CASE WHEN is_cancellation AND unit_price > 0 THEN -line_value ELSE 0 END) AS cancelled_value
        FROM tx{w} GROUP BY 1 ORDER BY 1""", p)
    m["cancellation_rate_pct"] = m.cancellation_invoices / (m.sale_invoices + m.cancellation_invoices).replace(0, float("nan")) * 100
    m["is_partial"] = m.year_month == e.partial_month
    cw, cp = _where(a, "is_cancellation AND is_product AND unit_price > 0", e)
    prod = e.df(f"SELECT stock_code, MAX(description) AS description, SUM(-quantity) AS cancelled_units, SUM(-line_value) AS cancelled_value FROM tx{cw} GROUP BY 1 ORDER BY 4 DESC LIMIT {int(a.top_n)}", cp)
    ci, si = int(m.cancellation_invoices.sum()), int(m.sale_invoices.sum())
    peak = m[~m.is_partial].sort_values("cancellation_invoices", ascending=False).head(5)
    return _out({"sale_invoices": si, "cancellation_invoices": ci,
                 "cancellation_invoice_rate_pct": _num(ci / (ci + si) * 100) if ci + si else None,
                 "cancelled_value": _num(m.cancelled_value.sum()), "cancelled_value_pct_of_sales": _num(m.cancelled_value.sum() / m.sales_value.sum() * 100) if m.sales_value.sum() else None},
                {"monthly": _rows(m, cap=60), "peak_months": _rows(peak), "top_cancelled_products": _rows(prod)},
                ["Rate = cancellation invoices / (sale invoices + cancellation invoices). Cancellations may refer to sales in earlier months.", *_partial_note(e)])


def get_quantity_analysis(e: Engine, a: TopN):
    w, p = _where(a, "is_sale", e)
    r = e.df(f"SELECT AVG(quantity) AS mean_q, MEDIAN(quantity) AS median_q, QUANTILE_CONT(quantity, 0.95) AS p95_q, MAX(quantity) AS max_q, SUM(quantity) AS units FROM tx{w}", p).iloc[0]
    m = e.df(f"SELECT year_month, SUM(quantity) AS units FROM tx{w} GROUP BY 1 ORDER BY 1", p)
    return _out({"units": _num(r.units, 0), "mean_line_quantity": _num(r.mean_q), "median_line_quantity": _num(r.median_q), "p95_line_quantity": _num(r.p95_q), "max_line_quantity": _num(r.max_q, 0)},
                {"monthly_units": _rows(m, cap=60)})


def _invoice_cte(w):
    return f"WITH inv AS (SELECT invoice, SUM(line_value) AS value, SUM(quantity) AS units, COUNT(*) AS lines FROM tx{w} GROUP BY 1)"


def get_average_invoice_value(e: Engine, a: Filters):
    w, p = _where(a, "is_sale", e)
    m = e.df(f"SELECT year_month, SUM(line_value) / COUNT(DISTINCT invoice) AS average_invoice_value, COUNT(DISTINCT invoice) AS invoices FROM tx{w} GROUP BY 1 ORDER BY 1", p)
    o = e.df(f"{_invoice_cte(w)} SELECT AVG(value) AS mean_v, MEDIAN(value) AS median_v FROM inv", p).iloc[0]
    return _out({"average_invoice_value": _num(o.mean_v), "median_invoice_value": _num(o.median_v)}, {"monthly": _rows(m, cap=60)})


def get_invoice_analysis(e: Engine, a: Filters):
    w, p = _where(a, "is_sale", e)
    r = e.df(f"""{_invoice_cte(w)} SELECT COUNT(*) AS invoices, AVG(value) AS mean_value, MEDIAN(value) AS median_value,
        QUANTILE_CONT(value, 0.95) AS p95_value, MAX(value) AS max_value, AVG(lines) AS mean_lines, AVG(units) AS mean_units,
        SUM(CASE WHEN lines = 1 THEN 1 ELSE 0 END) AS single_line_invoices FROM inv""", p).iloc[0]
    n = int(r.invoices)
    return _out({"invoices": n, "mean_invoice_value": _num(r.mean_value), "median_invoice_value": _num(r.median_value), "p95_invoice_value": _num(r.p95_value),
                 "max_invoice_value": _num(r.max_value), "mean_lines_per_invoice": _num(r.mean_lines), "mean_units_per_invoice": _num(r.mean_units),
                 "single_line_invoice_pct": _num(r.single_line_invoices / n * 100) if n else None},
                notes=["Aggregate distribution only; individual invoices are never returned."])


def get_product_concentration(e: Engine, a: Filters):
    w, p = _where(a, "is_sale", e)
    df = e.df(f"SELECT stock_code, SUM(line_value) AS revenue FROM tx{w} GROUP BY 1 ORDER BY 2 DESC", p)
    t = df.revenue.sum()
    if not t:
        return _out({"products": 0})
    cum = df.revenue.cumsum() / t * 100
    share = lambda k: _num(cum.iloc[min(k, len(df)) - 1])
    return _out({"products": len(df), "top_1_share_pct": share(1), "top_5_share_pct": share(5), "top_10_share_pct": share(10), "top_20_share_pct": share(20),
                 "products_for_80pct_revenue": int((cum < 80).sum() + 1), "products_for_80pct_revenue_share_of_catalogue_pct": _num(((cum < 80).sum() + 1) / len(df) * 100)})


def get_seasonality_analysis(e: Engine, a: Filters):
    w, p = _where(a, "is_sale", e)
    m = e.df(f"SELECT year_month, SUM(line_value) AS revenue FROM tx{w} GROUP BY 1 ORDER BY 1", p)
    m = m[m.year_month != e.partial_month]
    m["cal"] = m.year_month.str[5:]
    cal = m.groupby("cal").revenue.mean().reset_index()
    cal["seasonal_index"] = cal.revenue / cal.revenue.mean()
    cal = cal.rename(columns={"revenue": "avg_revenue", "cal": "calendar_month"})
    dow = e.df(f"SELECT EXTRACT(isodow FROM invoice_date) AS iso_weekday, SUM(line_value) AS revenue, COUNT(DISTINCT invoice) AS invoices FROM tx{w} GROUP BY 1 ORDER BY 1", p)
    hr = e.df(f"SELECT EXTRACT(hour FROM invoice_date) AS hour, COUNT(DISTINCT invoice) AS invoices FROM tx{w} GROUP BY 1 ORDER BY 1", p)
    pk = cal.sort_values("seasonal_index", ascending=False)
    return _out({"peak_calendar_month": None if pk.empty else pk.calendar_month.iloc[0], "peak_seasonal_index": None if pk.empty else _num(pk.seasonal_index.iloc[0]),
                 "trough_calendar_month": None if pk.empty else pk.calendar_month.iloc[-1], "trough_seasonal_index": None if pk.empty else _num(pk.seasonal_index.iloc[-1])},
                {"calendar_month_index": _rows(cal, 3), "weekday": _rows(dow), "hourly_invoices": _rows(hr)},
                ["Seasonal index 1.0 = average calendar month. Only two years of data, so seasonality is indicative.", "iso_weekday 1=Mon..7=Sun; the dataset has no Saturday trading in most weeks.", *_partial_note(e)])


class AnomalyArgs(Filters):
    metric: Literal["revenue", "invoices"] = "revenue"
    granularity: Literal["day", "month"] = "day"
    z_threshold: float = Field(3.0, ge=1.5, le=6)
    max_results: int = Field(10, ge=1, le=15)


def get_anomaly_summary(e: Engine, a: AnomalyArgs):
    w, p = _where(a, "is_sale", e)
    key = "CAST(invoice_date AS DATE)" if a.granularity == "day" else "year_month"
    df = e.df(f"SELECT {key} AS period, SUM(line_value) AS revenue, COUNT(DISTINCT invoice) AS invoices FROM tx{w} GROUP BY 1 ORDER BY 1", p)
    if a.granularity == "month":
        df = df[df.period != e.partial_month]
    df["period"] = df.period.astype(str)
    s = df[a.metric]
    sd = s.std()
    df["z_score"] = (s - s.mean()) / sd if sd and sd > 0 else 0.0
    an = df[df.z_score.abs() >= a.z_threshold].reindex(df.z_score.abs().sort_values(ascending=False).index).dropna().head(int(a.max_results))
    return _out({"periods_analysed": len(df), "anomalies_found": int((df.z_score.abs() >= a.z_threshold).sum()), "mean": _num(s.mean()), "std_dev": _num(sd), "z_threshold": a.z_threshold},
                {"anomalies": _rows(an)}, ["Z-score vs the mean of the selected window; flags unusual values, does not explain them."])


class TBArgs(Filters):
    dimension: Literal["product", "country", "month"] = "product"
    n: int = Field(5, ge=1, le=15)


def get_top_bottom_performers(e: Engine, a: TBArgs):
    w, p = _where(a, "is_sale", e)
    col = {"product": "stock_code, MAX(description) AS description", "country": "country", "month": "year_month"}[a.dimension]
    grp = {"product": "stock_code", "country": "country", "month": "year_month"}[a.dimension]
    df = e.df(f"SELECT {col}, SUM(line_value) AS revenue FROM tx{w} GROUP BY {grp} HAVING SUM(line_value) > 0", p)
    if a.dimension == "month":
        df = df[df.year_month != e.partial_month]
    df = df.sort_values("revenue", ascending=False)
    return _out({"dimension": a.dimension, "groups": len(df)}, {"top": _rows(df.head(a.n)), "bottom": _rows(df.tail(a.n).iloc[::-1])},
                ["Bottom performers only include groups with positive revenue."])


# ---------------------------------------------------------------- registry
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[[Engine, Any], dict]


def _t(name, desc, model, fn):
    return name, Tool(name, desc, model, fn)


TOOLS: dict[str, Tool] = dict([
    _t("get_dataset_overview", "Headline KPIs: records, invoices, revenue, products, countries, date range.", NoArgs, get_dataset_overview),
    _t("get_dataset_schema", "Columns, types and descriptions of the analysable dataset.", NoArgs, get_dataset_schema),
    _t("get_data_quality_report", "Counts of cleaning actions and data-quality issues.", NoArgs, get_data_quality_report),
    _t("get_revenue_summary", "Total revenue, invoices, units and average invoice value (optionally filtered).", Filters, get_revenue_summary),
    _t("get_revenue_trend", "Monthly revenue with month-over-month change and significant declines.", TrendArgs, lambda e, a: get_revenue_trend(e, a, a.decline_threshold_pct)),
    _t("get_period_comparison", "Compare revenue/invoices/avg invoice between two month ranges (B vs baseline A).", PeriodArgs, get_period_comparison),
    _t("get_product_performance", "Top products by revenue or units, plus products whose revenue declined recently.", ProductArgs, get_product_performance),
    _t("get_country_performance", "Revenue, share and average invoice by country.", TopN, get_country_performance),
    _t("get_cancellation_analysis", "Cancellation invoices/value by month, peak months and most-cancelled products.", TopN, get_cancellation_analysis),
    _t("get_quantity_analysis", "Distribution of units per sale line and monthly units.", TopN, get_quantity_analysis),
    _t("get_average_invoice_value", "Average and median invoice value overall and by month.", Filters, get_average_invoice_value),
    _t("get_invoice_analysis", "Invoice-level distribution: value percentiles, lines and units per invoice.", Filters, get_invoice_analysis),
    _t("get_product_concentration", "Share of revenue held by the top 1/5/10/20 products; products needed for 80% of revenue.", Filters, get_product_concentration),
    _t("get_seasonality_analysis", "Seasonal index by calendar month, weekday and hour patterns.", Filters, get_seasonality_analysis),
    _t("get_anomaly_summary", "Unusual days or months by z-score of revenue or invoice count.", AnomalyArgs, get_anomaly_summary),
    _t("get_top_bottom_performers", "Top and bottom products, countries or months by revenue.", TBArgs, get_top_bottom_performers),
])


def tool_specs() -> list[dict]:
    return [{"name": t.name, "description": t.description, "arguments_schema": t.args_model.model_json_schema()} for t in TOOLS.values()]


def validate_call(name: str, args: Any) -> tuple[Tool, BaseModel]:
    if not isinstance(name, str) or name not in TOOLS:
        raise ToolError(f"Unknown tool '{str(name)[:60]}'. Only registered analytical tools may be called.")
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be an object.")
    tool = TOOLS[name]
    try:
        return tool, tool.args_model.model_validate(args)
    except ValidationError as ex:
        msg = "; ".join(f"{'.'.join(map(str, er['loc']))}: {er['msg']}" for er in ex.errors()[:4])
        raise ToolError(f"Invalid arguments for {name}: {msg}") from None


def execute_tool(e: Engine, name: str, args: Any) -> dict:
    tool, model = validate_call(name, args)
    return tool.fn(e, model)
