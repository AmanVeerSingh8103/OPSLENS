import pandas as pd
import pytest

from opslens.ingest import SchemaError, clean
from opslens.tools import execute_tool


def test_cleaning_report_and_rules(raw, cleaned):
    df, rep = cleaned
    assert rep["dropped_invalid_date_qty_or_price"] == 1
    assert rep["dropped_exact_duplicates"] == 1
    assert rep["dropped_negative_price"] == 1
    assert "customer_id" not in df.columns
    assert rep["rows_clean"] == len(df)
    post = df[df.stock_code == "POST"].iloc[0]
    assert not post.is_sale and not post.is_product
    assert df[df.is_cancellation].is_sale.sum() == 0


def test_missing_columns_raise_schema_error():
    with pytest.raises(SchemaError):
        clean(pd.DataFrame({"Invoice": ["1"]}))


def test_revenue_matches_pandas(cleaned, engine):
    df = cleaned[0]
    expected = (df[df.is_sale].quantity * df[df.is_sale].unit_price).sum()
    got = execute_tool(engine, "get_dataset_overview", {})["metrics"]
    assert got["sales_revenue"] == pytest.approx(expected, abs=0.01)
    assert got["completed_invoices"] == df[df.is_sale].invoice.nunique()
    assert got["cancellation_invoices"] == df[df.is_cancellation].invoice.nunique()
    assert got["average_invoice_value"] == pytest.approx(expected / got["completed_invoices"], abs=0.01)


def test_period_comparison(cleaned, engine):
    df = cleaned[0]; s = df[df.is_sale]
    a = s[s.year_month.between("2010-01", "2010-03")].line_value.sum()
    b = s[s.year_month.between("2011-01", "2011-03")].line_value.sum()
    m = execute_tool(engine, "get_period_comparison", dict(a_start="2010-01", a_end="2010-03", b_start="2011-01", b_end="2011-03"))["metrics"]
    assert m["revenue_change_pct"] == pytest.approx((b - a) / a * 100, abs=0.01)


def test_cancellation_denominator(cleaned, engine):
    df = cleaned[0]
    ci, si = df[df.is_cancellation].invoice.nunique(), df[df.is_sale].invoice.nunique()
    m = execute_tool(engine, "get_cancellation_analysis", {})["metrics"]
    assert m["cancellation_invoice_rate_pct"] == pytest.approx(ci / (ci + si) * 100, abs=0.01)


def test_trend_flags_known_dip_and_excludes_partial(engine):
    r = execute_tool(engine, "get_revenue_trend", {})
    assert "2011-05" in [d["year_month"] for d in r["tables"]["significant_declines"]]
    assert "2011-12" not in [d["year_month"] for d in r["tables"]["significant_declines"]]


def test_all_tools_run_and_expose_no_identifiers(engine):
    from opslens.tools import TOOLS
    import json
    needs = {"get_period_comparison": dict(a_start="2010-01", a_end="2010-03", b_start="2011-01", b_end="2011-03")}
    for name in TOOLS:
        out = json.dumps(execute_tool(engine, name, needs.get(name, {}))).lower()
        assert "customer" not in out.replace("customer country", "") or name == "get_dataset_schema"
        assert '"invoice":' not in out and "invoiceno" not in out
