import sqlite3
import pandas as pd
from functions import get_prices

conn = sqlite3.connect("solar_dashboard.db")
#loading up our SQL database using "conn" as the connecting keyword

financials = pd.read_sql("SELECT * FROM financials", conn)
prices = pd.read_sql("SELECT * FROM stock_prices", conn)
#using conn and pandas' read_sql function to extract information from specific SQL tables and store them in new variables
#These new variables will be used to work with the data and find any and all issues with it

issues = []

print(prices.columns)

###########################################################################################################
#1. TAG TRANSITIONS
#This searches for multiple original EDGAR tags per ticker/metric
#Our existing financials table in SQL already has unified metric names
#As such, this check looks for potentially overlapping start/end dates per ticker/metric

for ticker in financials["ticker"].unique():
    #returns each distinct value in a column exactly once. Gives us a clean list of tickers to loop over
    for metric in ["Revenue", "NetIncomeLoss"]:
        #For every company, check both Revenue and NetIncomeLoss metrics separately
        subset = financials[(financials["ticker"] == ticker) & (financials["metric"] == metric)]
        #For each company we loop through, filter down to just that company's rows
        dupes = subset[subset.duplicated(subset = ["start", "end"], keep=False)]
        #Flags rows as duplocates based only on the column we name- in this case the start and end dates
        #keep=False flags every copy of a duplicate, so if a date appears twice, both rows get flagged as True
        #This returns a series of True/False, one per row in the subset variable
        if len(dupes) > 0:
            #If 1 or more dupes were found, append the issues list with the following:
            issues.append(f"{ticker}/{metric}: {len(dupes)} rows share a start/end date")

#.unique scans through ever vanue in a panda series (one column) and returns each distinct value exactly once
#it drops all repeats, but keeping the original order in which it first appears, not sorted or alphabetized

###########################################################################################################
#2. Missing years/gaps in sequence

for ticker in financials["ticker"].unique():
    for metric in ["Revenue", "NetIncomeLoss"]:
        subset = financials[(financials["ticker"] == ticker) & (financials["metric"] == metric)].copy()
        subset["year"] = pd.to_datetime(subset["end"]).dt.year
        #Convert text dates to real dates, then pull out just the year
        years = sorted(subset["year"].unique())
        #Get each distinct year this company/metric reported, sorted in order
        if len(years) > 1:
            #Generates every integet from the start date up to but not including the latest year and checks for gaps
            expected = set(range(years[0], years[-1] + 1))
            missing = expected - set(years)
            if missing:
                issues.append(f"{ticker} / {metric}: missing year(s) {sorted(missing)}")

###########################################################################################################
#3. Null or zero amounts
#Especially important for growth rate calculations!

zero_or_null = financials[(financials["amount"].isnull()) | (financials["amount"] == 0)]
#is.null returns True for any row were "amount" is missing or NaN
#financials["amount"] == 0 flags a row if its null or if its exactly 0
if len(zero_or_null) > 0:
    issues.append(f"{len(zero_or_null)} rows have a null or zero amount: {zero_or_null[['ticker','metric','end']].values.tolist()}")

###########################################################################################################
#4. Exact duplocate rows (all columns identical)

exact_dupes = financials[financials.duplicated(keep=False)]
#.duplicated(keep)=False with no subset argument checks for rows that are identical across every signle column, not just a chosen few like check 1
if len(exact_dupes) > 0:
    issues.append(f"{len(exact_dupes)} fully duplicate rows found")

###########################################################################################################
#5. Stock price gaps (fewer than 200 trading days in a full calendar year)

prices["year"] = pd.to_datetime(prices["date"]).dt.year
counts = prices.groupby(["Ticker", "year"]).size() if "Ticker" in prices.columns else prices.groupby(["ticker", "year"]).size()
#.groupby(["Ticker", "year"]).size() groups rows by both company and year, then counts how many rows fall into each group
low_years = counts[counts < 200]
#Checks how many groups have less than 200 entries
if len(low_years) > 0:
    issues.append(f"Years with unusually few trading days (may be partial-year/IPO, worth confirming): \n{low_years}")

###########################################################################################################
#Print report

print(f"\n--- AUDIT REPORT: {len(issues)} issues found ---\n")
for i, issue in enumerate(issues, 1):
    print(f"{i}. {issue}")

###########################################################################################################
#Searching for proper Revenue tags

from functions import get_cik
import requests
from config import TICKERS, HEADERS, TAGS
from functions import get_financials_for_ticker

headers = HEADERS
tickers_to_check = ["FSLR", "ENPH", "SEDG"]

for ticker in tickers_to_check:
    cik = get_cik(ticker, headers)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(url, headers=headers)
    edgar_data = response.json()

    gaap_keys = list(edgar_data["facts"]["us-gaap"].keys())
    revenue_tags = [key for key in gaap_keys if "Revenue" in key]

    print(ticker, ":", revenue_tags)

#clean_data already handles issues with overlap, but this is still handy to ensure whether different revenue tags
#have overlap in some years. This measures FSLR, which has no issues with overlap whatsoever
#This method is still useful, however, should our clean_data functions fail to catch a duplicate
#Such cases would exist if one tag's fiscal year started 01-01-2017 while another started 12-31-2016
#These would likely reference the same year, but clean_data would interpret them as different years entirely
all_financials = []
for ticker in TICKERS:
    company_financials = get_financials_for_ticker(ticker, TAGS, HEADERS)
    all_financials.append(company_financials)
financials_combined = pd.concat(all_financials, ignore_index=True)

fslr_check = financials_combined[
    (financials_combined["ticker"] == "FSLR") &
    (financials_combined["metric"].isin(["Revenues", "SalesRevenueGoodsNet", "SalesRevenueNet"]))
]
print(fslr_check[["start", "end", "val", "metric"]].sort_values("end"))

test = get_prices("FSLR", "1990-01-01", "2020-01-01")
print(test["Date"].min())