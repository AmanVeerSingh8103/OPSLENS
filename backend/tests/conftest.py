"""TEST-ONLY synthetic fixture. This data is generated inside the test suite and is never used by the app."""
import numpy as np
import pandas as pd
import pytest

from opslens.engine import Engine
from opslens.ingest import clean


def make_raw() -> pd.DataFrame:
    rows, inv = [], 500000
    rng = np.random.default_rng(1)
    months = pd.period_range("2010-01", "2011-12", freq="M")
    for mi, per in enumerate(months):
        base = 40 + (25 if per.month in (10, 11) else 0) - (30 if per == pd.Period("2011-05") else 0)
        for k in range(base):
            inv += 1
            day = pd.Timestamp(per.year, per.month, 1 + k % 27, 10 + k % 6)
            if per == pd.Period("2011-12") and day.day > 9:
                continue
            for j in range(1 + k % 3):
                rows.append((str(inv), f"{85000 + (k * 7 + j) % 40}A", f"PRODUCT {(k * 7 + j) % 40}", int(rng.integers(1, 20)), day,
                             float(round(1 + ((k * 7 + j) % 40) / 4, 2)), 12000 + k, "United Kingdom" if k % 5 else "France"))
            if k % 9 == 0:
                inv += 1
                rows.append((f"C{inv}", f"{85000 + k % 40}A", f"PRODUCT {k % 40}", -2, day, 2.5, 12000 + k, "United Kingdom"))
    rows.append(("600001", "POST", "POSTAGE", 1, pd.Timestamp("2010-03-03"), 18.0, 1, "United Kingdom"))
    rows.append(("600002", "85000A", None, 3, pd.Timestamp("2010-03-03"), -4.0, 1, "United Kingdom"))
    rows.append(("600003", "85001A", "BAD DATE", 3, "not-a-date", 2.0, 1, "United Kingdom"))
    rows.append(rows[0])  # exact duplicate
    return pd.DataFrame(rows, columns=["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"])


@pytest.fixture(scope="session")
def raw():
    return make_raw()


@pytest.fixture(scope="session")
def cleaned(raw):
    return clean(raw)


@pytest.fixture(scope="session")
def engine(cleaned, tmp_path_factory):
    d = tmp_path_factory.mktemp("proc")
    cleaned[0].to_parquet(d / "transactions.parquet", index=False)
    return Engine(d / "transactions.parquet")
