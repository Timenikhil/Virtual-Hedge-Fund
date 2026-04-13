import yfinance as yf

# List of Nifty 50 Tickers as of 2026
nifty50_tickers = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BEL.NS", "BPCL.NS",
    "BHARTIARTL.NS", "BRITANNIA.NS", "CIPLA.NS", "COALINDIA.NS", "DRREDDY.NS",
    "EICHERMOT.NS", "GRASIM.NS", "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS",
    "HEROMOTOCO.NS", "HINDALCO.NS", "HINDUNILVR.NS", "ICICIBANK.NS", "ITC.NS",
    "INDUSINDBK.NS", "INFY.NS", "JSWSTEEL.NS", "KOTAKBANK.NS", "LT.NS",
    "LTIM.NS", "M&M.NS", "MARUTI.NS", "NESTLEIND.NS", "NTPC.NS",
    "ONGC.NS", "POWERGRID.NS", "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS",
    "SUNPHARMA.NS", "TATACONSUM.NS", "TATASTEEL.NS", "TCS.NS",
    "TECHM.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS"
]

# Define timeframe (including 2026 data up to current date)
start_date = "2016-04-01"
end_date = "2026-03-31"

# Download data
print(f"Downloading OHLCV data for {len(nifty50_tickers)} stocks...")
data = yf.download(nifty50_tickers, start=start_date, end=end_date, group_by='ticker')


# Save to CSV for future use
data.to_csv("nifty50_historical_2020_2026.csv")
