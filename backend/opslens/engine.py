import json
import threading
from pathlib import Path

import duckdb
import pandas as pd


class DatasetNotReady(Exception):
    pass


class Engine:
    """Read-only DuckDB view over the cleaned Parquet. Only tools.py talks to it."""

    def __init__(self, parquet: Path):
        self.path = Path(parquet)
        if not self.path.exists():
            raise DatasetNotReady(
                "Processed dataset not found. Run `python -m opslens.ingest --download` "
                "(or place online_retail_II.xlsx in data/raw/ and run `python -m opslens.ingest`)."
            )
        self._lock = threading.Lock()
        self.con = duckdb.connect(":memory:")
        p = str(self.path).replace("'", "''")
        self.con.execute(f"CREATE VIEW tx AS SELECT * FROM read_parquet('{p}')")
        qr = self.path.parent / "quality_report.json"
        self.ingest_report = json.loads(qr.read_text()) if qr.exists() else {}
        self.countries = set(self.df("SELECT DISTINCT country FROM tx")["country"])
        last = self.df("SELECT MAX(invoice_date) d FROM tx")["d"].iloc[0]
        self.last_date = pd.Timestamp(last)
        months = list(self.df("SELECT DISTINCT year_month FROM tx ORDER BY 1")["year_month"])
        self.partial_month = months[-1] if self.last_date.day < self.last_date.days_in_month else None
        self.months = months
        self.complete_months = [m for m in months if m != self.partial_month]

    def df(self, sql: str, params=()) -> pd.DataFrame:
        with self._lock:
            return self.con.execute(sql, list(params)).fetchdf()
