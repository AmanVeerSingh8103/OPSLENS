"""Dataset ingestion: UCI Online Retail II (xlsx) -> cleaned Parquet.

Cleaning decisions (also written to quality_report.json):
 1. Column names normalised (Invoice/InvoiceNo, Price/UnitPrice, Customer ID/CustomerID).
 2. Rows with unparseable InvoiceDate, Quantity or Price are dropped (counted).
 3. Exact duplicate rows (all raw columns) are dropped (counted).
 4. Rows with negative UnitPrice (bad-debt adjustments) are dropped (counted).
 5. Invoices starting with 'C' are cancellations (is_cancellation). Never counted as sales.
 6. A line is a *sale* (is_sale) only if: not a cancellation, Quantity > 0, UnitPrice > 0 and
    StockCode starts with 5 digits (real product). Postage, fees, manual adjustments, samples
    and test codes are therefore excluded from revenue.
 7. Zero-price lines and non-cancellation negative quantities are kept but flagged, not sales.
 8. Missing descriptions are kept (description = NULL), counted.
 9. CustomerID is used only to count missing values and is DROPPED from the processed data, so
    no downstream tool can expose it.
Revenue = Quantity x UnitPrice over sale lines. It is revenue, not profit.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from .config import get_settings

UCI_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
COLUMN_MAP = {
    "Invoice": "invoice", "InvoiceNo": "invoice", "StockCode": "stock_code",
    "Description": "description", "Quantity": "quantity", "InvoiceDate": "invoice_date",
    "Price": "unit_price", "UnitPrice": "unit_price", "Customer ID": "customer_id",
    "CustomerID": "customer_id", "Country": "country",
}
REQUIRED = {"invoice", "stock_code", "description", "quantity", "invoice_date", "unit_price", "customer_id", "country"}

MANUAL_INSTRUCTIONS = (
    "Download 'Online Retail II' from https://archive.ics.uci.edu/dataset/502/online+retail+ii "
    "(CC BY 4.0, DOI 10.24432/C5CG6D), unzip it and place online_retail_II.xlsx in data/raw/, "
    "then run: python -m opslens.ingest"
)


class SchemaError(Exception):
    pass


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = raw.rename(columns={c: COLUMN_MAP[c] for c in raw.columns if c in COLUMN_MAP}).copy()
    missing = REQUIRED - set(df.columns)
    if missing:
        raise SchemaError(f"Dataset is missing required columns: {sorted(missing)}")
    df = df[sorted(REQUIRED)]
    rep: dict = {"rows_raw": int(len(df))}

    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    bad = df["invoice_date"].isna() | df["quantity"].isna() | df["unit_price"].isna()
    rep["dropped_invalid_date_qty_or_price"] = int(bad.sum())
    df = df[~bad]

    dups = df.duplicated(keep="first")
    rep["dropped_exact_duplicates"] = int(dups.sum())
    df = df[~dups]

    neg_price = df["unit_price"] < 0
    rep["dropped_negative_price"] = int(neg_price.sum())
    df = df[~neg_price]

    for c in ("invoice", "stock_code", "country"):
        df[c] = df[c].astype(str).str.strip()
    df["description"] = df["description"].astype("string").str.strip()
    df.loc[df["description"].isin(["", "nan", "<NA>"]), "description"] = pd.NA
    rep["missing_description"] = int(df["description"].isna().sum())
    rep["missing_customer_id"] = int(df["customer_id"].isna().sum())
    df = df.drop(columns=["customer_id"])

    df["is_cancellation"] = df["invoice"].str.upper().str.startswith("C")
    df["is_product"] = df["stock_code"].str.match(r"^\d{5}")
    df["is_sale"] = (~df["is_cancellation"]) & (df["quantity"] > 0) & (df["unit_price"] > 0) & df["is_product"]
    df["line_value"] = (df["quantity"] * df["unit_price"]).astype(float)
    df["year_month"] = df["invoice_date"].dt.strftime("%Y-%m")

    rep.update(
        rows_clean=int(len(df)),
        cancellation_lines=int(df["is_cancellation"].sum()),
        sale_lines=int(df["is_sale"].sum()),
        zero_price_lines=int((df["unit_price"] == 0).sum()),
        non_cancellation_negative_quantity_lines=int(((~df["is_cancellation"]) & (df["quantity"] < 0)).sum()),
        non_product_lines=int((~df["is_product"]).sum()),
    )
    return df.reset_index(drop=True), rep


def read_workbook(path: Path) -> pd.DataFrame:
    sheets = pd.read_excel(path, sheet_name=None, dtype={"Invoice": str, "InvoiceNo": str, "StockCode": str})
    return pd.concat(sheets.values(), ignore_index=True)


def download(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    zpath = raw_dir / "online_retail_ii.zip"
    urllib.request.urlretrieve(UCI_URL, zpath)  # noqa: S310 - fixed official URL
    with zipfile.ZipFile(zpath) as z:
        z.extractall(raw_dir)
    found = list(raw_dir.glob("*.xlsx"))
    if not found:
        raise FileNotFoundError("No .xlsx found in downloaded archive")
    return found[0]


def prepare(xlsx: Path, out_dir: Path) -> dict:
    df, rep = clean(read_workbook(xlsx))
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "transactions.parquet", index=False)
    rep["source"] = "UCI Online Retail II, DOI 10.24432/C5CG6D, CC BY 4.0, creator Daqing Chen"
    (out_dir / "quality_report.json").write_text(json.dumps(rep, indent=2))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prepare the Online Retail II dataset")
    ap.add_argument("--file", type=Path, help="Path to online_retail_II.xlsx")
    ap.add_argument("--download", action="store_true", help="Download from the official UCI URL")
    a = ap.parse_args(argv)
    s = get_settings()
    raw_dir = s.data_dir / "raw"
    try:
        xlsx = a.file or (download(raw_dir) if a.download else next(iter(raw_dir.glob("*.xlsx")), None))
        if xlsx is None:
            print("No raw workbook found.\n" + MANUAL_INSTRUCTIONS, file=sys.stderr)
            return 2
        rep = prepare(Path(xlsx), s.data_dir / "processed")
    except Exception as e:  # noqa: BLE001
        print(f"Ingestion failed: {type(e).__name__}: {e}\n{MANUAL_INSTRUCTIONS}", file=sys.stderr)
        return 1
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
