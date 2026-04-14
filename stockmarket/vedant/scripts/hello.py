import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from backtesting import Strategy, Backtest
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()
data = tv.get_hist(
    symbol='AAPL',
    exchange='NASDAQ',
    interval=Interval.in_1_minute,
    n_bars= 50
)

period = 14 

high = data['high']
low = data['low']
close = data['close']

prev_close = close.shift(1)

tr1 = high - low
tr2 = (high - prev_close).abs()
tr3 = (low - prev_close).abs()
true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

data['atr'] = true_range.rolling(window=period).mean()

print(data[['close', 'atr']].tail())  # preview

data.to_csv('AAPL_1min_with_ATR.csv')
print("Saved to AAPL_1min_with_ATR.csv")

print(data)

go.Figure(go.Candlestick(
    x=data.index,
    open=data['open'],
    high=data['high'],
    low=data['low'],
    close=data['close']
)).show()