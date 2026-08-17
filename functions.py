import pandas as pd
import yfinance as yf
import requests
import sqlite3

###########################################################################################################################
def get_annual_financials(edgar_data, tag):
#This function expects edgar_data to already be in the dictionary
#tag is a parameter- a placeholder input that lets this function work for any us-gaap line item, rather than only working for revenue or net income

    """
    Pulls a clean, deduplicated annual history for a given us-gaap tag
    (e.g., "Revenues" or "NetIncomeLoss) from a an EDGAR companyfacts response
    """
    #This is a docstring- a special string after a function definition that documents what it does
    #VS Code will show this text as a tooltip when someone hovers over the function name elsewhere in the code

    tag_data = edgar_data["facts"]["us-gaap"][tag]
    #opens up edgar_data, then opens facts, then opens us_gaap and stores the contents of that package inside of tag_data
    #"tag" is modular. When we run this function we put an input in for "tag" that can be, say, "Revenues", or "NetIncomeLoss"
    #"tag" simply holds whatever value we assign it when running the code from the outside
    usd_values = tag_data["units"]["USD"]
    #Further breaks open tag_data to open up units then open up USD
    #This can be condensed into usd_values = edgar_data["facts"]["us-gaap"][tag]["units"]["USD"] if desired, but the current form is more readable

    records = []
    for entry in usd_values:
        records.append ({
            "start": entry["start"],
            "end": entry["end"],
            "val": entry["val"],
            "fy_filed_in": entry["fy"],
            "form": entry["form"]
            })
    
    df = pd.DataFrame(records)
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    df["duration_days"] = (df["end"] - df["start"]).dt.days

    annual = df[
        (df["form"] == "10-K") &
        (df["duration_days"] > 300) &
        (df["end"].dt.year == df["fy_filed_in"])
    ].copy()
    #This is all the standard sifting process from before
    #It ensures that the years and statements we draw are not duplicates and contain the correct information of the correct type

    annual["metric"] = tag
    #This creats a column labeling which financial metric the DataFrame represents
    #This way, we won't mix up revenue and income should we use this function to get both
    #It uses the tag we assign when running it to clarify what kind of information we are receiving

    return annual

###########################################################################################################################
def get_prices(ticker, start, end):
    #ticker, start, and end, are parameters that we will input when we call this function
    """
    Pulls daily price data for a given ticker between a set start/end date
    Returns a clean, flat dataframe
    """
    data = yf.download(ticker, start=start, end=end, interval="1d")
    #The inputs here are all from yahood finance. The leftmost portions of start=start, end=end, etc., are its parameters for extracting data

    data.columns = data.columns.get_level_values(0)
    #Flattens the MultiIndex down to get plain names
    data.columns.name = None
    #Removes the added tags leftover from flattening the MultiIndex
    #Without this, we would see "price" over the entry numbers. It is a name, not a column header or part of an index
    #This line tells pandas to eliminate all names, but not column or index headers

    data["Ticker"] = ticker
    data = data.reset_index()
    #adds a Ticker column and turns the date index into a real column

    return data
#This last line sends data frame back out to whoever called the function. Needed to hold the data we retrieve

###########################################################################################################################
def get_cik(ticker, headers):
    """
    Looks up a firm's 10-digit CIK number from SEC EDGAR's ticker-to-CIK matching file
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers = headers)
    all_companies = response.json()

    for company in all_companies.values():
        if company["ticker"] == ticker.upper():
            return str(company["cik_str"]).zfill(10)
    return None

###########################################################################################################################
#Finds the CIK for a ticker and pulls that company's financials
def get_financials_for_ticker(ticker, tags, headers):
    #this function must be supplied with three parameters:
    #the ticker, the tag (a list of strings like []"Revenues", "NetIncomeLoss"]), and our headers (identification information to access EDGAR)
    """
    Given a ticker, looks up its CIK, fetches its EDGAR data once,
    and pulls annual histories for each requested us-gaap tag.
    Returns one combined DataFrame with a 'metric' column distinguishing tags
    """
    cik = get_cik(ticker, headers)
    if cik is None:
        print(f"Warning: no CIK found for {ticker}")
        return pd.DataFrame
    #Uses get_cik to retrieve the CIK, returning an empty data frame if no matches are found
    #If no match is found, it prints a warning, but because it still returns an empty data frame, it doesn't stop the whole code immediately
    
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(url, headers=headers)
    edgar_data = response.json()
    #Builds the URL using the CIK we just retrieved, then parses the json response into a python dictionary

    results = []
    #creates an empty list reader to collect one data frame per tag as the next loop runs
    for tag in tags:
        #loops the code through whatever tags were passed in. So "tag" will hold "Revenues" on the first pass and "NetIncomeLoss" on the second, assuming those tags were entered
        try:
            df = get_annual_financials(edgar_data, tag)
            df["ticker"] = ticker
            results.append(df)
        except KeyError:
            print(f"Warning: {ticker} has no data for tag '{tag}'")
        #Appends the data frame with all information gathered as per the tags
        #If a tag turns up nothing, a warning is printed but only for that specific tag
    
    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    #This final line combines everything in "results" into one data frame, assuming results has something in it
    #Elsewise, it just returns an empy dataframe

###########################################################################################################################
#Returns the stock price return information for a company or companies surrounding a specific date
def get_event_window_return(ticker, event_date, cursor, window=5):
    """
    Given a ticker and a policy event date, finds the closest trading day
    on/after that date, then calculates the % price return from `window`
    trading days before to `window` trading days after.
    Returns a dictionary with the key details, or None if there isn't
    enough data on either side of the event.
    """
    #If no window value is entered, it defaults to a window of 5 tradings days + or - the entry of the input date

    #First, we must find the day_num of the trading day on/after the event:
    cursor.execute("""
        WITH ranked_prices AS (
            SELECT ticker, date, close,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date) AS day_num
            FROM stock_prices
            WHERE ticker = ?
        )
        SELECT day_num FROM ranked_prices
        WHERE date >= ?
        ORDER BY date
        LIMIT 1
    """, (ticker, event_date))
    #WHERE ticker = ? is what is called a "paramaterized query." It is how we insert Python variables into SQL. We do the same for date >=?
    #At the end of the query, in parenthesis, is the tupled pair of variables we are passing throw. They go in order, matching ? to each corresponding tuple item

    result = cursor.fetchone()
    if result is None:
        return None 
    #no trading data on/after this event for this ticker
    
    event_day_num = result[0]
    #Pulls whatever sits at position 0- in this case, the entry number for the anchor date

    #Then, we must pull the price window days before and after that anchor
    cursor.execute("""
        WITH ranked_prices AS (
            SELECT ticker, date, close,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date) AS day_num
            FROM stock_prices
            WHERE ticker = ?
        )
        SELECT
            (SELECT close FROM ranked_prices WHERE day_num = ?) AS price_before,
            (SELECT close FROM ranked_prices WHERE day_num = ?) AS price_after
    """, (ticker, event_day_num - window, event_day_num + window))

    row = cursor.fetchone()
    if row is None or row[0] is None or row[1] is None:
        return None  
    #not enough trading days before/after (such as if the event too close to start/end of data)

    price_before, price_after = row
    pct_return = round((price_after - price_before) * 100.0 / price_before, 2)

    #This returns all final data including the ticker and event date
    return {
        "ticker": ticker,
        "event_date": event_date,
        "price_before": price_before,
        "price_after": price_after,
        "pct_return": pct_return
    }

###########################################################################################################################
#Checks the current state of the SQL database
#For both of these functions, conn is a parameter. This lets the function be modular, as we can pass in whatever connecting the calling script already has open

def get_last_price_date(ticker, conn):
    """
    Returns the most recent date already stored in stock_prices for this
    ticker, or None if the ticker has no data yet (first-time fetch).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(date) FROM stock_prices WHERE ticker = ?", (ticker,))
    #Seeks the latest date for the ticker we input
    result = cursor.fetchone()
    return result[0]
    #this final line is what our fetch loop will check. If no existing dat is found, it will do a full historical fetch on the stock data we are seeking

def get_last_financial_period(ticker, conn):
    """
    Returns the most recent 'end' date already stored in financials for
    this ticker, or None if the ticker has no financials data yet.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(end) FROM  financials WHERE ticker = ?", (ticker,))
    result = cursor.fetchone()
    return result[0]