"""
clean_data.py

Consolidates all data cleaning steps discovered during Weeks 1-5:
- Standardizes revenue tag names into one consistent 'Revenue' label
- Removes duplicate rows that arise when a company transitions between
  two different EDGAR tags for the same underlying metric (e.g., NEE)
- Standardizes column name casing across tables (yfinance returns
  capitalized names; our schema design uses lowercase)

  ...

FUTURE ENHANCEMENT:
Currently, revenue tag names are hardcoded in config.py's REVENUE_TAGS list,
discovered through manual investigation per company (see FSLR, ENPH, ARRY,
SHLS, NEE, RUN). This works but doesn't scale automatically- a newly
added company reporting under an unrecognized tag would silently return
incomplete or missing revenue data.

A more robust version would combine data from ALL matching tags (not just
one "best" tag), deduplicate overlapping periods automatically, and flag
two warning conditions: (1) any unrecognized "Revenue"-like tag not in
REVENUE_TAGS, and (2) gaps in the resulting year sequence. Sketched out
but deliberately deferred until after the core project is complete, to
avoid over-engineering before the basic pipeline works end-to-end.
"""
#This is a module-level docstring. It is the same concept as a regular docstring, but applied to an entire file rather than a single function

#############################################################################################
#These are our two active cleaning functions

import pandas as pd

def clean_financials(financials_df):
    """"
    Takes a raw financials DataFrame (as returned by get_financials_for_ticker,
    concatenated across companies) and returns a cleaned version:
    - Unifies revenue tag names under one 'Revenue' label
    - Drops exact duplicate rows that result from tag transitions
    - Renames columns to their final, intended names
    """
    df = financials_df.copy()

    df["metric"] = df ["metric"]. replace ({
        "Revenues": "Revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
        "RegulatedAndUnregulatedOperatingRevenue": "Revenue",
        "SalesRevenueGoodsNet": "Revenue",
        "SalesRevenueNet": "Revenue"
    })

    df = df.drop_duplicates(subset=["ticker","start","end","metric"], keep="first")

    df = df.rename(columns={
        "val": "amount",
        "fy_filed_in": "fiscal_year_filed"
    })

    df = df.drop(columns=["duration_days"])
    #removes an unintentionally added table called "duration_days" that cause problems later on

    return df

def clean_prices(prices_df):
     """
    Takes a raw prices DataFrame (as returned by get_prices, concatenated
    across companies) and returns a cleaned version with standardized,
    lowercase column names.
    """
     df = prices_df.copy()
     df.columns = [col.lower() for col in df.columns]
     #for every column name in the DataFrame, coverts it to lowercase
     #This fixes inconsistencies with ticker/Ticker, date/Date column names
     return df