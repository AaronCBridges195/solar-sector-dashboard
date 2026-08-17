
#This file exists to fetch, clean, create the schema, and load. The orchestration script will take care of doing all that in the right order

import sqlite3
import pandas as pd
from config import TICKERS, HEADERS, TAGS
from functions import get_prices, get_financials_for_ticker, get_last_financial_period, get_last_price_date
from clean_data import clean_financials, clean_prices
import datetime
import logging
from logging.handlers import RotatingFileHandler
#This is a submodule inside the logging package. It contains more specialized "handlers" build to automatically manage file size
import time



def run_build():
    """
    Fetches new stock prices and financials incrementally, cleans them,
    and loads them into solar_dashboard.db. Returns a summary dictionary
    with counts of new rows added.
    """
    handler = RotatingFileHandler("pipeline.log", maxBytes=1_000_000, backupCount=5)
    #Creates a handler object stored in variable "handler"
    #A handler in Python's logging system is responsible for where log messages go and how they're written/stored
    #This handler limits the bytes to 1,000,000 bytes, which is one mb. It allows up to 5 old, rotated-out log files to keep before deleting the oldest
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    #Creates a formatting object called logging.formatter, which contains the following format and is then attached to the handler object we just created
    #formats the logged output as, for example, 2026-07-17 14:32:01 - INFO - Fetched FSLR
    #We have to build the formatter as a separate object because we are using a custom handler

    logging.basicConfig(level=logging.INFO, handlers=[handler])
    #We place our custom handler inside basicConfig. It can hold multiple handlers, which is why it is a list
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    #silences yfinance's own internal logging system which presumes errors when trying to retrieve information mid-trading day
    #Unless the error is classified as CRITICAL

    logger = logging.getLogger(__name__)
    #This is the oject we call when passing information through to the pipeline

    conn = sqlite3.connect("solar_dashboard.db")

    today = datetime.date.today().strftime("%Y-%m-%d")
    #fetches today's date and returns it as a string within the variable "today"

    #############################################################################################
    #First, we fetch, clean, and upload prices to SQL

    all_new_prices = []
    for ticker in TICKERS:
        try:
            #We wrap the entire per-ticker loop block so if anything goes wrong for a specific ticker, the except will catch it and log it as a clear error
            #Then, the look will continue to the next ticker rather than crashing the entire script
            last_date = get_last_price_date(ticker, conn)

            if last_date is None:
                start_date = "1990-01-01"
            else:
                last_dt = pd.to_datetime(last_date)
                start_date = (last_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                #sets the start date one day up from the last entry. if there is no new data after last entry, nothing is retrieved and an error is logged
                #datetime.timedelta takes a date and moves it forward by one
                #.strftime changes the date to a string, which can be understood by yfinance

            prices = get_prices(ticker, start_date, today)
            #takes the input ticker and the decided start date decided by the if/else above and gathers the information
            #The start date will either be in 1990 or the latest entry that exists in our storage. Today, of course, is today

            if len(prices) > 0:
                all_new_prices.append(prices)
                logger.info(f"{ticker}: fetched {len(prices)} new price rows")
                #replaces print calls. .info logs routine, expected events and writes them down in pipeline.log
            elif last_date is None:
                logger.warning(f"{ticker}: first-time fetch return 0 rows. Possible invalid ticker")
                #If after pulling new data, there still exists no last_date for the ticker, log this warning message
                #If a nonexistent ticker is put in, we should get this warning message as opposed to the latter
            else:
                logger.info(f"{ticker}: no new price rows to fetch")

        except Exception as e:
            #Exception is a catchall covering almost all error types. Useful because a failure here can manifest in numerous ways
            logger.error(f"{ticker}: price fetch failed - {e}")
            #Catches errors specifically, writing their occurrence in pipeline.log
            #as e captures the actual error object, letting us read the error message
    
    if all_new_prices:
        new_prices_combined = clean_prices(pd.concat(all_new_prices, ignore_index=True))
        new_prices_combined.to_sql("stock_prices", conn, if_exists="append", index=False)

    #############################################################################################
    #Then, we do the same for financials

    all_new_financials = []
    for ticker in TICKERS:
        try:
            last_period = get_last_financial_period(ticker, conn)
            company_financials = get_financials_for_ticker(ticker, TAGS, HEADERS)

            if last_period is not None:
                company_financials = company_financials[company_financials["end"]>last_period]
                #If we do indeed have financial data, only grab rows with an end date after the last period we already have stored

            if len(company_financials) > 0:
                all_new_financials.append(company_financials)
                logger.info(f"{ticker}: fetched {len(company_financials)} new financial rows")
            else:
                logger.info(f"{ticker}: no new financial rows to fetch")
        
        except Exception as e:
            logger.error(f"{ticker}: financials fetch failed - {e}")
        
        time.sleep(0.25)
        #Pauses the script's execution for 0.25 seconds before continuting to the next line
        #Here at the end of the loop, it tells python to fetch a ticker's information, wait 0.25 seconds, then move on to the next ticker
        #EDGAR permits only 10 requests a second, meaning we need at least 0.1 seconds between each request
        #As such, we want to sit in a comfortable safety margin. With 7 companies, this barely adds any runtime to the script

    if all_new_financials:
        new_financials_combined = clean_financials(pd.concat(all_new_financials, ignore_index=True))
        new_financials_combined.to_sql("financials", conn, if_exists="append", index = False)

    #Unlike yfinance, EDGAR's API doesn't let us request only filings after X date. We must always get the entire filing history back in one JSON block
    #Instead of avoiding the fetch, we simply fetch everything and then filter after the fact to keep only rows newer than what we already have

    new_price_count = len(new_prices_combined) if all_new_prices else 0
    new_financial_count = len(new_financials_combined) if all_new_financials else 0

    conn.close()

    return {
        "new_price_rows": new_price_count,
        "new_financial_rows": new_financial_count
    }