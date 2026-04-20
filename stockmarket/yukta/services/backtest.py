from tvDatafeed import TvDatafeed, Interval
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd
import ta

# =========================
# GET DATA
# =========================
def get_tv_data(symbol="BTCUSD", exchange="BITSTAMP",
                interval=Interval.in_5_minute, n_bars=2000):

    tv = TvDatafeed()
    df = tv.get_hist(symbol=symbol, exchange=exchange,
                     interval=interval, n_bars=n_bars)
    
    if df is None:
        raise Exception("Data not fetched from TradingView")
    
    print("DF Value:", df)

    df = df.reset_index()

    df = df.rename(columns={
        "datetime": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })

    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


# =========================
# SMMA
# =========================
def smma(series, period):
    result = [None] * len(series)
    result[period - 1] = series[:period].mean()

    for i in range(period, len(series)):
        result[i] = (result[i - 1] * (period - 1) + series[i]) / period

    return pd.Series(result, index=series.index)


# =========================
# FEATURES
# =========================
def add_features(df):
    df = df.copy()

    df["EMA_8"] = df["Close"].ewm(span=8).mean()
    df["EMA_14"] = df["Close"].ewm(span=14).mean()
    df["EMA_50"] = df["Close"].ewm(span=50).mean()

    df["MEDIAN"] = (df["High"] + df["Low"]) / 2
    df["LIPS"] = smma(df["MEDIAN"], 5).shift(3)

    df["EMA_CROSS_UP"] = (df["EMA_8"] > df["EMA_14"]) & (df["EMA_8"].shift(1) <= df["EMA_14"].shift(1))
    df["EMA_CROSS_DOWN"] = (df["EMA_8"] < df["EMA_14"]) & (df["EMA_8"].shift(1) >= df["EMA_14"].shift(1))

    df["RSI"] = ta.momentum.RSIIndicator(df["Close"], window=14).rsi()
    df["ADX"] = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=14).adx()

    return df


# =========================
# SIGNALS (IMPROVED)
# =========================
def ema_alligator_signals(df):
    df = df.copy()

    df["signal"] = None
    position = None
    entry_price = 0

    STOP_LOSS = 0.005   # 0.5%
    TARGET = 0.01       # 1%

    for i in range(1, len(df)):

        close = df["Close"].iloc[i]
        ema14 = df["EMA_14"].iloc[i]
        ema50 = df["EMA_50"].iloc[i]
        lips = df["LIPS"].iloc[i]
        rsi = df["RSI"].iloc[i]
        adx = df["ADX"].iloc[i]

        cross_up = df["EMA_CROSS_UP"].iloc[i]
        cross_down = df["EMA_CROSS_DOWN"].iloc[i]

        body = abs(df["Close"].iloc[i] - df["Open"].iloc[i])
        range_ = df["High"].iloc[i] - df["Low"].iloc[i]
        strong = (range_ > 0) and (body / range_ > 0.5)

        if pd.isna(lips) or pd.isna(rsi) or pd.isna(adx):
            continue

        # ======================
        # ENTRY
        # ======================
        if position is None:

            if (cross_up and close > lips and close > ema50
                    and rsi > 55 and adx > 20 and strong):

                df.loc[i, "signal"] = "BUY"
                position = "BUY"
                entry_price = close

            elif (cross_down and close < lips and close < ema50
                  and rsi < 45 and adx > 20 and strong):

                df.loc[i, "signal"] = "SELL"
                position = "SELL"
                entry_price = close

        # ======================
        # BUY MANAGEMENT
        # ======================
        elif position == "BUY":

            # STOP LOSS
            if close <= entry_price * (1 - STOP_LOSS):
                df.loc[i, "signal"] = "EXIT_BUY"
                position = None

            # TARGET HIT
            elif close >= entry_price * (1 + TARGET):
                df.loc[i, "signal"] = "EXIT_BUY"
                position = None

            # EARLY EXIT
            elif close < ema14:
                df.loc[i, "signal"] = "EXIT_BUY"
                position = None

        # ======================
        # SELL MANAGEMENT
        # ======================
        elif position == "SELL":

            # STOP LOSS
            if close >= entry_price * (1 + STOP_LOSS):
                df.loc[i, "signal"] = "EXIT_SELL"
                position = None

            # TARGET HIT
            elif close <= entry_price * (1 - TARGET):
                df.loc[i, "signal"] = "EXIT_SELL"
                position = None

            # EARLY EXIT
            elif close > ema14:
                df.loc[i, "signal"] = "EXIT_SELL"
                position = None

    return df

# =========================
# SUMMARY
# =========================
def process_transactions(df):
    trades = []
    position = None
    entry_price = 0

    for i in range(len(df)):
        signal = df["signal"].iloc[i]
        price = df["Close"].iloc[i]

        # ENTRY
        if signal == "BUY":
            position = "BUY"
            entry_price = price

        elif signal == "SELL":
            position = "SELL"
            entry_price = price

        # EXIT BUY
        elif signal == "EXIT_BUY" and position == "BUY":
            pnl = price - entry_price
            trades.append(pnl)
            position = None

        # EXIT SELL
        elif signal == "EXIT_SELL" and position == "SELL":
            pnl = entry_price - price
            trades.append(pnl)
            position = None

    trades = pd.Series(trades)

    # =========================
    # SAFE HANDLING
    # =========================
    if trades.empty:
        print("\n===== SUMMARY =====")
        print("No trades executed")
        return

    wins = trades[trades > 0]
    losses = trades[trades <= 0]

    total_trades = len(trades)
    win_rate = (len(wins) / total_trades) * 100
    total_pnl = trades.sum()

    avg_win = wins.mean() if not wins.empty else 0
    avg_loss = losses.mean() if not losses.empty else 0

    # =========================
    # PRINT CLEAN SUMMARY
    # =========================
    print("\n===== STRATEGY SUMMARY =====")
    print(f"Total Trades : {total_trades}")
    print(f"Win Rate     : {round(win_rate, 2)} %")
    print(f"Total PnL    : {round(total_pnl, 2)}")
    print(f"Avg Win      : {round(avg_win, 2)}")
    print(f"Avg Loss     : {round(avg_loss, 2)}")

from plotly.subplots import make_subplots
import plotly.graph_objects as go

# =========================
# PLOT FUNCTION
# =========================
from plotly.subplots import make_subplots
import plotly.graph_objects as go

def plot_chart(df):

    fig = make_subplots(rows=1, cols=1)

    # =========================
    # Candlestick (Styled)
    # =========================
    fig.add_trace(go.Candlestick(
        x=df["Date"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Candles",
        increasing_line_color="#00ff9f",   # green
        decreasing_line_color="#ff4d4d"    # red
    ))

    # =========================
    # EMA LINES
    # =========================
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["EMA_8"],
        mode='lines', name='EMA 8',
        line=dict(color="#00bfff", width=1)
    ))

    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["EMA_14"],
        mode='lines', name='EMA 14',
        line=dict(color="#ffa500", width=1)
    ))

    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["EMA_50"],
        mode='lines', name='EMA 50',
        line=dict(color="#ff00ff", width=1)
    ))

    # =========================
    # ALLIGATOR (LIPS)
    # =========================
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["LIPS"],
        mode='lines', name='Alligator Lips',
        line=dict(color="yellow", width=1)
    ))

    # =========================
    # BUY SIGNAL
    # =========================
    buy = df[df["signal"] == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy["Date"], y=buy["Close"],
        mode='markers',
        marker=dict(symbol='triangle-up', size=10, color='#00ff9f'),
        name='BUY'
    ))

    # =========================
    # SELL SIGNAL
    # =========================
    sell = df[df["signal"] == "SELL"]
    fig.add_trace(go.Scatter(
        x=sell["Date"], y=sell["Close"],
        mode='markers',
        marker=dict(symbol='triangle-down', size=10, color='#ff4d4d'),
        name='SELL'
    ))

    # =========================
    # EXIT BUY
    # =========================
    exit_buy = df[df["signal"] == "EXIT_BUY"]
    fig.add_trace(go.Scatter(
        x=exit_buy["Date"], y=exit_buy["Close"],
        mode='markers',
        marker=dict(symbol='x', size=8, color='yellow'),
        name='EXIT BUY'
    ))

    # =========================
    # EXIT SELL
    # =========================
    exit_sell = df[df["signal"] == "EXIT_SELL"]
    fig.add_trace(go.Scatter(
        x=exit_sell["Date"], y=exit_sell["Close"],
        mode='markers',
        marker=dict(symbol='x', size=8, color='yellow'),
        name='EXIT SELL'
    ))

    # =========================
    # DARK THEME LAYOUT
    # =========================
    fig.update_layout(
        title="EMA + Alligator Strategy",

        # Background
        plot_bgcolor="#0b0f1a",
        paper_bgcolor="#0b0f1a",

        # Font
        font=dict(color="white"),

        # Grid
        xaxis=dict(
            title="Date",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)",
            zeroline=False
        ),
        yaxis=dict(
            title="Price",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)",
            zeroline=False
        ),

        # Legend
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="white")
        )
    )

    # =========================
    # RETURN FOR DJANGO
    # =========================
    return fig.to_html(full_html=False)

def generate_roi_data(df):
    trades = []
    times = []
    position = None
    entry_price = 0

    for i in range(len(df)):
        signal = df["signal"].iloc[i]
        price = df["Close"].iloc[i]
        time = df["Date"].iloc[i]

        if signal == "BUY":
            position = "BUY"
            entry_price = price

        elif signal == "SELL":
            position = "SELL"
            entry_price = price

        elif signal == "EXIT_BUY" and position == "BUY":
            pnl = price - entry_price
            trades.append(pnl)
            times.append(time)
            position = None

        elif signal == "EXIT_SELL" and position == "SELL":
            pnl = entry_price - price
            trades.append(pnl)
            times.append(time)
            position = None

    if len(trades) == 0:
        return None

    trades = pd.Series(trades)
    cumulative = trades.cumsum()

    # ROI % (assuming base capital 1000 for visualization)
    capital = 1000
    roi = (cumulative / capital) * 100

    return {
        "times": times,
        "roi": roi,
        "total_pnl": round(trades.sum(), 2),
        "roi_overall": round(roi.iloc[-1], 2),
        "total_trades": len(trades)
    }



def plot_roi_graph(roi_data):

    fig = go.Figure()

    roi_values = roi_data["roi"]

    colors = ["#00ff9f" if x >= 0 else "#ff4d4d" for x in roi_values]

    fig.add_trace(go.Scatter(
        x=roi_data["times"],
        y=roi_values,
        mode='lines',
        line=dict(color="#00ff9f", width=2),
        fill='tozeroy',
        fillcolor="rgba(0,255,159,0.1)",
        name="Cumulative ROI %"
    ))

    fig.update_layout(
        title="ROI Graph",

        plot_bgcolor="#0b0f1a",
        paper_bgcolor="#0b0f1a",
        font=dict(color="white"),

        xaxis=dict(
            title="Time",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)"
        ),
        yaxis=dict(
            title="ROI %",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)"
        ),

        legend=dict(font=dict(color="white"))
    )

    return fig.to_html(full_html=False)

def generate_trade_log(df):
    trades = []
    position = None
    entry_price = 0

    for i in range(len(df)):
        signal = df["signal"].iloc[i]
        price = df["Close"].iloc[i]

        # ENTRY
        if signal == "BUY":
            position = "BUY"
            entry_price = price

        elif signal == "SELL":
            position = "SELL"
            entry_price = price

        # EXIT BUY
        elif signal == "EXIT_BUY" and position == "BUY":
            trades.append({
                "type": "BUY",
                "entry": round(entry_price, 2),
                "exit": round(price, 2),
                "pnl": round(price - entry_price, 2)
            })
            position = None

        # EXIT SELL
        elif signal == "EXIT_SELL" and position == "SELL":
            trades.append({
                "type": "SELL",
                "entry": round(entry_price, 2),
                "exit": round(price, 2),
                "pnl": round(entry_price - price, 2)
            })
            position = None

    return trades

# =========================
# MAIN
# =========================
def run_backtest():
    df = get_tv_data()
    df = add_features(df)
    df = ema_alligator_signals(df)

    chart_html = plot_chart(df)

    # ROI
    roi_data = generate_roi_data(df)

    if roi_data:
        roi_chart = plot_roi_graph(roi_data)
    else:
        roi_chart = None

    trades_list = generate_trade_log(df)

    wins = [t for t in trades_list if t["pnl"] > 0]
    total_trades = len(trades_list)

    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

    return {
        "strategy": "EMA Alligator Strategy",

        # Chart
        "chart": chart_html,

        # ROI SECTION
        "roi_chart": roi_chart,
        "roi_overall": roi_data["roi_overall"] if roi_data else 0,
        "total_pnl": roi_data["total_pnl"] if roi_data else 0,
        "total_trades": roi_data["total_trades"] if roi_data else 0,
        "trades": trades_list,
        "win_rate": round(win_rate, 2)
    }
if __name__ == "__main__":
    run_backtest()