import streamlit as st
import pandas as pd
import sqlite3
import altair as alt

st.set_page_config(page_title="Solar Sector Dashboard", layout="wide")
#configures the browser's tab title and tells Streamlit to use the full width of the screen
#Full width is better for dashboards with charts and tables side by side

conn = sqlite3.connect("solar_dashboard.db")

st.title("Solar Sector Financial Dashboard")
#renders a large page heading

###########################################################################
#Sidebar filters

companies_df = pd.read_sql("SELECT ticker, name, sector FROM companies", conn)
all_tickers = companies_df["ticker"].tolist()
#.tolist is a pandas method that converts a series (one column) to a plain Python list
#This is important because st.multiselect expects a plain list for its options

st.sidebar.header("Filters")
#Sets the header of sidebar, which is created on its own by simply saying "sidebar"
selected_tickers = st.sidebar.multiselect(
    #Creates the dropdown with checkboxes control. Options is the full list of possible choices
    #Default includes what all is selected whe nthe page first loads up
    #Whatever the user has checked gets returned and stored in selected_tickers
    #Since the script reruns with each user interactions, this will cause the whole scene to update with the desired info
    #this second use of sidebar ensures all included options are again displayed in the sidebar
    "Companies",
    options=all_tickers,
    default=all_tickers
)

min_date = pd.read_sql("SELECT MIN(date) as min_date FROM stock_prices", conn)["min_date"][0]
max_date = pd.read_sql("SELECT MAX(date) as max_date FROM stock_prices", conn)["max_date"][0]
#Here we define the min/max possible dates from the info stored in SQL

today_ts = pd.Timestamp.now().normalize()
#Allows us to have the max day be the current day, even if our data doesn't stretch that far
#This lets us use Streamlit's "2 years back" etc. features
#.normalize strips away the time-of-day element that includes hours, minutes, and seconds. This leaves only the calendar date

date_range = st.sidebar.date_input(
    "Date range",
    value=(pd.to_datetime(min_date), pd.to_datetime(max_date)),
    min_value=pd.to_datetime(min_date),
    max_value=today_ts
)
#This creates a range picker for a period between 2 dates

#st.write("Selected companies", selected_tickers)
#st.write("Date range:", date_range)
#These two lines are temporary; they let us visually confirm our filters are working
#st.write is a general purpose display function. it works with just about everything and autoformats its text

#We can run this code by entering "streamlit run app.py"

###########################################################################
#Summary cards

if selected_tickers:
    placeholders = ",".join(["?"]*len(selected_tickers))
    #Builds a string of question marks matching however many companies are selected
    #SQL's IN() function needs one ? per value when using parameterized queries
    #Since the number of selcted companies changes dynamically, we can't hardcode a fixed number of ?s

    growth_query = f"""
        WITH ranked AS (
            SELECT ticker, end, amount,
                   LAG(amount) OVER (PARTITION BY ticker ORDER BY end) AS prior_amount
            FROM financials
            WHERE metric = 'Revenue' AND ticker IN ({placeholders})
        )
        SELECT ticker, ROUND((amount - prior_amount) * 100.0 / prior_amount, 2) AS growth_pct
        FROM ranked
        WHERE prior_amount IS NOT NULL
        ORDER BY end DESC
    """
    #WHERE metric = 'Revenue' AND ticker IN ({placeholders}) inserts the ?s into SQL

    growth_df = pd.read_sql(growth_query, conn, params=selected_tickers)
    #Retrieves the calculation from SQL using params= to designate which tickers we are concerned with
    #These tickers are matched up with the ?s we entered earlier as placeholders

    if len(growth_df)>0:
        latest_growth = growth_df.sort_values("growth_pct", ascending=False).iloc[0]
        #.iloc[0] accesses rows by their first position- starting here with 0=first row
        #Then, after sorting growth by descending, iloc grabs the single highest growth row
        top_growth_ticker = latest_growth["ticker"]
    else:
        top_growth_ticker = "N/A"
    
    margin_query = f"""
        WITH revenue AS (
            SELECT ticker, end, amount AS revenue_amt
            FROM financials WHERE metric = 'Revenue' AND ticker IN ({placeholders})
        ),
        income AS (
            SELECT ticker, end, amount AS income_amt
            FROM financials WHERE metric = 'NetIncomeLoss' AND ticker IN ({placeholders})
        )
        SELECT revenue.ticker, ROUND(income.income_amt * 100.0 / revenue.revenue_amt, 2) AS margin_pct
        FROM revenue
        JOIN income ON revenue.ticker = income.ticker AND revenue.end = income.end
        ORDER BY revenue.end DESC
    """
    margin_df = pd.read_sql(margin_query, conn, params=selected_tickers + selected_tickers)
    #Because this query requests both revenue and income data, we must add a second set of selected tickers to retrieve that info

    if len(margin_df) > 0: 
        best_margin=margin_df.sort_values("margin_pct", ascending=False).iloc[0]
        top_margin_ticker=best_margin["ticker"]
    else:
        top_margin_ticker = "N/A"

else:
    top_growth_ticker = "N/A"
    top_margin_ticker = "N/A"

col1, col2, col3, col4 = st.columns(4)
#Splits the page horizonally into 4 separate equal side-by-side sections, lettus us place a card in each
col1.metric("Companies tracked", len(selected_tickers))
col2.metric("Top revenue growth", top_growth_ticker)
col3.metric("Most profitable", top_margin_ticker)
col4.metric("Data last refreshed", pd.Timestamp.now().strftime("%b %d"))
#Inserts information into those columns left to right

###########################################################################
#Price chart with policy events overlaid

st.subheader("Stock price history")

if selected_tickers and len(date_range) == 2:
    #and len(date_range) == 2 ensures that an error screen doesn't pop up while we only have one date selected
    #Rather, the graph will only appear when we have a start and end date selected
    start_date, end_date = date_range
    #date_range is a tuple, allowing us to unpack it into 2 variables

    price_placeholders = ",".join(["?"] * len(selected_tickers))
    price_query = f"""
        SELECT ticker, date, close
        FROM stock_prices
        WHERE ticker IN ({price_placeholders})
        AND date BETWEEN ? AND ?
        ORDER BY date
    """
    #AND date BETWEEN ? AND ? slots those 2 date variables into the SQL query

    price_params = selected_tickers + [str(start_date), str(end_date)]
    prices_df = pd.read_sql(price_query, conn, params=price_params)

    events_query = "SELECT event_date, description FROM policy_events WHERE event_date BETWEEN ? AND ?"
    events_df = pd.read_sql(events_query, conn, params=[str(start_date), str(end_date)])

    if len(prices_df) > 0:
        prices_df["date"] = pd.to_datetime(prices_df["date"])
        events_df["event_date"] = pd.to_datetime(events_df["event_date"])

        line_chart = alt.Chart(prices_df).mark_line().encode(
            #Here, we build the line chart
            #Altair builds a chart by chaining pieces together; alt.chart(prices_df) tells it what location to draw from
            #encode maps the data's columns to visual properties, denoting which variable is x versus y
            x="date:T",
            #T tells Altair that this column is temporal, so it knows to format the x axis as dates
            y="close:Q",
            #Tells Altair that this column is quantitative, so it knows to show the close price as a regular number
            color="ticker:N"
            #N means nominal (a catagory, not a number). This makes Altair automatically draw a differently colored line per company
            #also builds a legend like pivot and st.line_chart
        )

        if len(events_df) > 0:
            event_lines = alt.Chart(events_df).mark_rule(color="gray", strokeDash=[4, 4]).encode(
                #Here, we build the events chart
                x="event_date:T",
                tooltip="description:N"
                #Marks the line as a grey, dotted line, denotes that it is on the x axis, and tells that hovering it should show a tooltip with the event's description
            )
            combined_chart = (line_chart + event_lines).properties(height=400)
            #layers both the line_chart and the even_lines chart on top of one another- sharing the same x axis
            #This matches them up by date
        else:
            combined_chart = line_chart.properties(height=400)
            #If no events are listed, then onlt the line_chart will show

        st.altair_chart(combined_chart, use_container_width=True)
    else:
        st.info("No price data available for the selected companies and date range.")
else:
    st.info("Select at least one company and a full date range to view price history.")

###########################################################################
#Comparison table

st.subheader("Company comparison")

if selected_tickers and len(date_range) == 2:
    start_date, end_date = date_range
    comparison_placeholders = ",".join(["?"] * len(selected_tickers))
    
    comparison_query = f"""
        WITH revenue AS (
            SELECT ticker, end, amount AS revenue_amt,
                   LAG(amount) OVER (PARTITION BY ticker ORDER BY end) AS prior_revenue
            FROM financials
            WHERE metric = 'Revenue' AND ticker IN ({comparison_placeholders})
        ),
        income AS (
            SELECT ticker, end, amount AS income_amt
            FROM financials
            WHERE metric = 'NetIncomeLoss' AND ticker IN ({comparison_placeholders})
        ),
        latest_year AS (
            SELECT ticker, MAX(end) AS latest_end
            FROM financials
            WHERE metric = 'Revenue' AND ticker IN ({comparison_placeholders})
            AND end BETWEEN ? AND ?
            GROUP BY ticker
        )
        SELECT companies.ticker, companies.sector,
               revenue.revenue_amt,
               ROUND(income.income_amt * 100.0 / revenue.revenue_amt, 2) AS net_margin_pct,
               ROUND((revenue.revenue_amt - revenue.prior_revenue) * 100.0 / revenue.prior_revenue, 2) AS revenue_growth_pct
        FROM latest_year
        JOIN revenue ON latest_year.ticker = revenue.ticker AND latest_year.latest_end = revenue.end
        JOIN income ON revenue.ticker = income.ticker AND revenue.end = income.end
        JOIN companies ON revenue.ticker = companies.ticker
        ORDER BY revenue_growth_pct DESC
    """
    #Here, we've got 3 CTEs: revenue, income, and latest_year. The first two extract what you'd expect from SQL
    #Latest year pulls the company's most recent revenue-reporting year
    #Then, we join all three in the following form: latest_year>revenue>income>companies
    #We narrow down the result slowly, first by finding the last reporting year for each firm, then that year's revenue, and then that year's net income and finally sector info

    comparison_params = selected_tickers * 3 + [str(start_date), str(end_date)]
    #Creates 3 copies of the tickers we insert to fulfill those three CTE queries
    comparison_df = pd.read_sql(comparison_query, conn, params=comparison_params)
    
    if len(comparison_df) > 0:
        comparison_df.columns = ["Ticker", "Sector", "Revenue", "Net margin %", "Revenue growth %"]
        #directly reassigns the whole column list at once, as opposed to renaming them which can cause pathing issues
        st.dataframe(comparison_df, use_container_width=True, hide_index=True)
         #Steamlit's table rendering widget
    else:
        st.info("No financial data for the selected companies and date range.")
else:
    st.info("Select at least one company and a full date range to view the comparison table.")

###########################################################################
#Revenue growth bar chart

st.subheader("Revenue growth by year")

if selected_tickers and len(date_range) == 2:
    start_date, end_date = date_range
    growth_placeholders = ",".join(["?"] * len(selected_tickers))
    
    growth_history_query = f"""
        WITH ranked AS (
            SELECT ticker, end, amount,
                   LAG(amount) OVER (PARTITION BY ticker ORDER BY end) AS prior_amount
            FROM financials
            WHERE metric = 'Revenue' AND ticker IN ({growth_placeholders})
        )
        SELECT ticker, end,
               ROUND((amount - prior_amount) * 100.0 / prior_amount, 2) AS growth_pct
        FROM ranked
        WHERE prior_amount IS NOT NULL
        AND end BETWEEN ? AND ?
        ORDER BY ticker, end
    """
    #WHERE prior_amount IS NOT NULL filters out every company's first year, as there's nothing to calculate growth against

    growth_history_params = selected_tickers + [str(start_date), str(end_date)]
    growth_history_df = pd.read_sql(growth_history_query, conn, params=growth_history_params)
    
    if len(growth_history_df) > 0:
        growth_history_df["end"] = pd.to_datetime(growth_history_df["end"])
        growth_history_df["year"] = growth_history_df["end"].dt.year
        
        growth_chart = alt.Chart(growth_history_df).mark_bar().encode(
            x=alt.X("year:O", title="Year"),
            #O means ordinal- treating years as discrete categories in a fixed order, rather than a continuous number
            #Vital for a bar chart
            y=alt.Y("growth_pct:Q", title="Revenue growth (%)"),
            color="ticker:N",
            xOffset="ticker:N",
            #Makes multiple companies' bars sit side by side. Elsewise, Altair would just draw them on top of one another
            tooltip=["ticker:N", "year:O", "growth_pct:Q"]
            #Lets us see the company, year, and percentage when we mouse over any bar
        ).properties(height=350)
        
        st.altair_chart(growth_chart, use_container_width=True)

    else:
        st.info("No revenue growth data for the selected companies and date range.")
else:
    st.info("Select at least one company and a full date range to view revenue growth history.")

###########################################################################
#Revenue vs. net income by company

st.subheader("Revenue vs. net income by company")

if selected_tickers and len(date_range) == 2:
    start_date, end_date = date_range
    rev_income_placeholders = ",".join(["?"] * len(selected_tickers))
    
    rev_income_query = f"""
        SELECT ticker, end, metric, amount
        FROM financials
        WHERE metric IN ('Revenue', 'NetIncomeLoss')
        AND ticker IN ({rev_income_placeholders})
        AND end BETWEEN ? AND ?
        ORDER BY ticker, end
    """
    #WHERE metric IN ('Revenue', 'NetIncomeLoss') pulls both metrics in one query
    #Being that these metrics are meant to be side by side, it makes little sense to separate them into 2 different tables then rejoin them

    rev_income_params = selected_tickers + [str(start_date), str(end_date)]
    rev_income_df = pd.read_sql(rev_income_query, conn, params=rev_income_params)
    
    if len(rev_income_df) > 0:
        rev_income_df["end"] = pd.to_datetime(rev_income_df["end"])
        rev_income_df["year"] = rev_income_df["end"].dt.year
        rev_income_df["metric"] = rev_income_df["metric"].replace({
            "NetIncomeLoss": "Net income"
            #Cosmetic- relabels the raw database value into something more readable for the chart legend
        })
        
        
        lines = alt.Chart(rev_income_df).mark_line(point=True).encode(
            #mark_line(point=True) adds visible dots at each actual datapoint along the line, which lets us see more clearly where datapoints are
            x=alt.X("year:O", title="Year"),
            y=alt.Y("amount:Q", title="Amount ($)"),
            color=alt.Color("metric:N", title="Metric"),
            #Colors both lines by metric
            tooltip=["ticker:N", "year:O", "metric:N", "amount:Q"]
        )

        zero_line = alt.Chart(rev_income_df).mark_rule(color="gray", strokeDash=[2, 2]).encode(
            y=alt.datum(0)
        )
        #creates a horizontal line at point 0
        
        layered = (lines + zero_line).properties(width=300, height=250)
        #conjoins that horizontal line with the income/revenue chart

        faceted = layered.facet(
            facet=alt.Facet("ticker:N", title=None),
            #names each chart after its company ticker and removes any overarching title
            columns=3
        )

        st.altair_chart(faceted, use_container_width=True)
    else:
        st.info("No revenue/income data for the selected companies and date range.")











