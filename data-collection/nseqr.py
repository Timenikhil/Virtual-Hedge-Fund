import pandas as pd
import numpy as np

# 1. Load the raw yfinance CSV
df = pd.read_csv("nifty50_historical_2020_2026.csv", header=[0, 1], index_col=0)

# 2. Reshape to Long format
df_long = df.stack(level=0).reset_index()
df_long.columns = ['Date', 'Sid','Open','High','Low', 'Close','Volume']

# 4. Grouped Forward Fill (Prevent data leakage between different stocks)
# Sort by Sid and Date first to ensure chronological filling
df_long = df_long.sort_values(['Sid', 'Date'])

price_cols = ['Open', 'High', 'Low', 'Close']
# Forward fill prices per stock
df_long[price_cols] = df_long.groupby('Sid')[price_cols].ffill()

# Fill Volume with 0 (If it didn't trade, volume is zero, not the previous day's volume)
df_long['Volume'] = df_long.groupby('Sid')['Volume'].transform(lambda x: x.fillna(0))

# 5. Format for QuantRocket
df_long['Date'] = pd.to_datetime(df_long['Date']).dt.strftime('%Y-%m-%d')
final_df = df_long[['Date', 'Sid', 'Open', 'High', 'Low', 'Close', 'Volume']]

# 6. Save for Import
final_df.to_csv("nifty50_ffill_adjusted.csv", index=False)

print("Pre-processing complete with Grouped Forward Fill.")
print(final_df.groupby('Sid').tail(3)) # Preview last 3 rows per stock
