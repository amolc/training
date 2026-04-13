


from tvDatafeed import TvDatafeed, Interval

import pandas as pd
import numpy as np

import plotly.io as pio
from plotly.subplots import make_subplots

from pandas_ta import ta






def tvdata(symbol,exchange,interval,n_bars):
    
    tv = TvDatafeed()
    df = tv.get_hist(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        n_bars=n_bars,
    )
    
    return df


def run():
    symbol = "BTCUSD"
    exchange = "BINANCE"
    interval = Interval.in_1_minute
    n_bars = 100

    # Step 1 : get the data 
    df = tvdata(symbol,exchange,interval,n_bars)

    # output
    
    df.reset_index(inplace=True)
    print(df.head())

