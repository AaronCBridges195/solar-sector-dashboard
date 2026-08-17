"""
run_pipeline.py

The single entry point for refreshing the solar dashboard's data.
Run this script (manually, or via a scheduled task) to fetch any new
stock prices and financial filings, clean them, and load them into
solar_dashboard.db.
"""

from build_db import run_build

if __name__ == "__main__":
    print("Starting pipeline run...")
    summary = run_build()
    print(f"Pipeline complete: {summary['new_price_rows']} new price rows, "
          f"{summary['new_financial_rows']} new financial rows added.")
    print("See pipeline.log for full details.")