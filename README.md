# Solar Sector Financial Dashboard

An interactive dashboard analyzing how solar and renewable energy companies' financial performance responds to federal policy changes, built end-to-end in Python, from raw SEC filings and market data to a live, filterable Streamlit app.

![Dashboard screenshot](images/dashboard-screenshot.png)

## What this does

This project tracks 7 publicly traded solar/renewable companies (First Solar, Enphase, SolarEdge, Sunrun, NextEra Energy, Array Technologies, and Shoals Technologies), pulling their stock prices and financial filings directly from Yahoo Finance and the SEC's EDGAR API. It cleans and reconciles that data (which turns out to be far messier than it first appears) into a normalized SQLite database, then serves it through an interactive dashboard that lets you compare revenue growth, profitability, and stock performance around real federal policy events like the Inflation Reduction Act.

## Features

**Live-filtered dashboard** select any combination of companies and a date range; every chart and table updates accordingly
**Price chart with policy events overlaid** see exactly how a company's stock moved in the days surrounding a specific policy announcement
**Company comparison table** revenue, net margin, and YoY growth, side by side
**Revenue growth by year** a bar chart per company, letting you see multi-year trends rather than a single snapshot
**Revenue vs. net income, faceted by company** a small chart per selected company, with a zero-reference line, making it easy to spot years where a company had strong revenue but still posted a loss
**Incremental, scheduled data refresh** the pipeline only fetches what's new since the last run, logs its own activity, and is designed to run unattended via a daily scheduled task

## Tech stack

Python · pandas · SQLite · SQL (window functions, CTEs, multi-table joins) · Streamlit · Altair · SEC EDGAR API · yfinance

## Architecture

[SEC EDGAR API] [yfinance]
\ /
v v
Python ETL scripts (fetch)
|
v
Cleaning & standardization
(tag reconciliation, dedup)
|
v
SQLite database
(companies, stock_prices, financials, policy_events)
|
SQL queries (joins, window
functions, CTEs)
|
v
Streamlit dashboard

## Setup

1. Clone this repository and navigate into it.
2. Create and activate a virtual environment:
    python -m venv venv
    venv\Scripts\Activate.ps1 # Windows
    source venv/bin/activate # Mac/Linux
3. Install dependencies:
    pip install pandas requests yfinance streamlit altair
4. Build the database (fetches full history — this will take a few minutes on first run):
    python run_pipeline.py
5. Launch the dashboard:
    streamlit run app.py

## Project structure

final_dash/
    config.py # Company list, EDGAR headers, revenue tag mappings
    functions.py # Reusable fetch functions (prices, financials, CIK lookup)
    clean_data.py # Data cleaning: tag standardization, deduplication
    build_db.py # Fetch, clean, and load logic (wrapped as run_build())
    run_pipeline.py # Entry point — run this to refresh all data
    app.py # The Streamlit dashboard itself
    solar_dashboard.db # SQLite database (included for convenience)

## Data sources

- **Stock prices** — [yfinance](https://github.com/ranaroussi/yfinance), wrapping Yahoo Finance
- **Financial statements** — [SEC EDGAR's company facts API](https://www.sec.gov/edgar/sec-api-documentation), pulling structured data directly from filed 10-Ks
- **Policy events** — hand-curated, currently covering the 2022 Inflation Reduction Act signing, a 2023 Section 201 tariff renewal, and 2024 antidumping duties on Southeast Asian solar imports

## A note on data cleaning

Getting from raw EDGAR filings to a clean, comparable dataset was most of the actual engineering work in this project. A few things worth knowing:

- **Companies report revenue under different XBRL tags depending on when they adopted ASC 606 and their filer type.** This project reconciles multiple tag variants (`Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `RegulatedAndUnregulatedOperatingRevenue`, and older pre-2018 tags like `SalesRevenueNet`) into a single, continuous `Revenue` metric per company.
- **Some companies transitioned between tags mid-history**, which initially produced duplicate rows for the transition year (identical period, two different tag names). This is detected and deduplicated automatically.
- **CSIQ (Canadian Solar) and JKS (JinkoSolar) are excluded from financials**  both are foreign private issuers, likely filing under Form 20-F rather than a standard 10-K, which this pipeline doesn't currently parse.
- **Array Technologies' 2020 price data covers only ~54 trading days**  this is correct, not missing data; the company IPO'd in October 2020.

## Known limitations & future improvements

- Revenue tag discovery is currently manual. A new company added to the universe may report under an unrecognized tag, silently returning incomplete data. A more robust version (sketched in `clean_data.py` but deliberately not implemented, to avoid over-engineering before the core pipeline worked end-to-end) would pull from *every* matching tag automatically and flag any unrecognized "Revenue"-like tags or gaps in the resulting year sequence.
- Foreign private issuers (CSIQ, JKS) are excluded rather than supported.
- Policy events are hand-curated rather than pulled from a live source.

## Adding a new company

1. Add the ticker to `TICKERS` in `config.py`.
2. Run `python run_pipeline.py`.
3. If the company's revenue doesn't appear, check the warnings printed to `pipeline.log` — it likely reports under a tag not yet in `REVENUE_TAGS`. Search its EDGAR `us-gaap` keys for anything containing `"Revenue"`, and add the correct tag to `config.py`.

## Automation

`run_pipeline.py` is designed to run unattended via a scheduled task (Windows Task Scheduler / cron). It fetches only new data since the last run, logs its activity to a rotating `pipeline.log`, and skips any individual ticker that fails rather than halting the entire run.