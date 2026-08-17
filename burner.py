"""
backfill_prices.py

One-time script to backfill stock price history further back than the
original 2020 starting point. Run once; not part of the regular
incremental pipeline (build_db.py already handles ongoing updates).
"""

import sqlite3
import pandas as pd
from config import TICKERS
from functions import get_prices
from clean_data import clean_prices

conn = sqlite3.connect("solar_dashboard.db")

all_backfill = []
for ticker in TICKERS:
    existing_dates = pd.read_sql(
        "SELECT date FROM stock_prices WHERE ticker = ?", conn, params=(ticker,)
    )["date"].tolist()

    full_history = get_prices(ticker, "1990-01-01", "2020-01-01")

    if len(full_history) == 0:
        print(f"{ticker}: no pre-2020 history available")
        continue

    full_history_clean = clean_prices(full_history)
    new_rows = full_history_clean[~full_history_clean["date"].isin(existing_dates)]

    if len(new_rows) > 0:
        all_backfill.append(new_rows)
        print(f"{ticker}: adding {len(new_rows)} backfilled rows")
    else:
        print(f"{ticker}: no earlier history to backfill")

if all_backfill:
    backfill_combined = pd.concat(all_backfill, ignore_index=True)
    backfill_combined.to_sql("stock_prices", conn, if_exists="append", index=False)

conn.close()