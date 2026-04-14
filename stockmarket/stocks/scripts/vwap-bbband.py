


from tvDatafeed import TvDatafeed, Interval

import pandas as pd
import numpy as np

import plotly.io as pio
import plotly.graph_objects as go
from plotly.subplots import make_subplots


import stocks.quant as quant


Quant = quant.Quant()




def tvdata(symbol,exchange,interval,n_bars):
    
    tv = TvDatafeed()
    df = tv.get_hist(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        n_bars=n_bars,
    )
    
    return df



def graph(df):
            # numberofrows = len(df.index)
            # if numberofrows > 600:
            #     df = df[-200:]
            fig = go.Figure()

            # df['datetime'] = df['datetime'] + timedelta(hours=8)
            # declare figure
            # Create subplots and mention plot grid size

            fig = make_subplots(
                rows=1,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.1,
                subplot_titles=("OHLC", "Volume"),
            )



            # fig.add_trace(go.Scatter(x=df['index'], y=df['supertrend'], line_shape='spline', line_smoothing=1.3,
            #                         line=dict(color='blue', width=.7), name='close'), row=1, col=1)
            try:   
                fig.add_trace(go.Scatter(x=df['index'], y=df['finalc2_lowerband'], line_shape='spline', line_smoothing=1.3,
                                    line=dict(color='green', width=.7), name='close'), row=1, col=1)
            except:
                print("no attributes as finalc2_upperband")


            try:
                fig.add_trace(go.Scatter(x=df['index'], y=df['finalc2_upperband'], line_shape='spline', line_smoothing=1.3,
                                line=dict(color='red', width=.7), name='close'), row=1, col=1)
            except:
                print("no attributes as finalc2_upperband")

            try:
                fig.add_trace(go.Scatter(x=df['index'], y=df['close'], line_shape='spline', line_smoothing=1.3,
                                    line=dict(color='blue', width=.7), name='close'), row=1, col=1)
            except:
                print("no attributes as finalc2_upperband")

            # try:
            #     fig.add_trace(go.Scatter(x=df['index'], y=df['ma'], line_shape='spline', line_smoothing=1.3,
            #                         line=dict(color='orange', width=.7), name='ma'), row=1, col=1)
            # except:
            #     print("no attributes as finalc2_upperband")



            # try:
            #     fig.add_trace(go.Scatter(x=df['index'], y=df['ema'], line_shape='spline', line_smoothing=1.3,
            #                                 line=dict(color='purple', width=.7), name='ema'), row=1, col=1)
            # except:
            #     print("no attribute")
            
            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["buy"],
                        mode="markers",
                        name="buy",
                        line=dict(width=1, color="green"),
                    ),row=1, col=1
                )
            except:
                print("no attributes as buy")

            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["buyclose"],
                        mode="markers",
                        name="buyclose",
                        line=dict(width=1, color="darkblue"),
                        
                    ),row=1, col=1
                )
            except:
                print("no attributes as buy")

            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["sell"],
                        mode="markers",
                        name="sell",
                        line=dict(width=1, color="red"),
                    ),row=1, col=1
                )
            except:
                print("no attributes as sell")


            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["sellclose"],
                        mode="markers",
                        name="sellclose",
                        line=dict(width=1, color="orange"),
                    ),row=1, col=1
                )
            except:
                print("no attributes as sellclose")


            fig.update_layout(title="Stock Analysis", yaxis_title="OHLC", height=900, width=1500)
            fig.update(layout_xaxis_rangeslider_visible=False)
            fig.show()




def run():
    symbol = "ETHUSD"
    exchange = "BINANCE"
    interval = Interval.in_1_minute
    n_bars = 100

    # Step 1 : get the data 
    df = tvdata(symbol,exchange,interval,n_bars)

    # output
    
    df.reset_index(inplace=True)

    atr_period = 14

    df["atr"] = atr = df["close"].ewm(alpha=1 / atr_period, min_periods=atr_period).mean()
    df.to_csv(f"btcusd.csv", index=False)
    Quant.save2googlesheet(df, "Vwap", 0)

    # df = Quant.checkbuysell(df)
    
    print(df.head())





