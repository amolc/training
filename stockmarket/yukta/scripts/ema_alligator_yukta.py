from tvDatafeed import TvDatafeed, Interval
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd
import ta

# =========================
# GET DATA
# =========================
def get_tv_data(symbol="BTCUSD", exchange="COINBASE",
                interval=Interval.in_5_minute, n_bars=2000):

    tv = TvDatafeed()
    df = tv.get_hist(symbol=symbol, exchange=exchange,
                     interval=interval, n_bars=n_bars)

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
def add_features(df, params):
    df = df.copy()

    ema_8 = int(params.get("ema_8", 8))
    ema_14 = int(params.get("ema_14", 14))
    ema_50 = int(params.get("ema_50", 50))

    lips_period = int(params.get("lips_period", 5))
    lips_shift = int(params.get("lips_shift", 3))

    df["EMA_8"] = df["Close"].ewm(span=ema_8).mean()
    df["EMA_14"] = df["Close"].ewm(span=ema_14).mean()
    df["EMA_50"] = df["Close"].ewm(span=ema_50).mean()

    df["MEDIAN"] = (df["High"] + df["Low"]) / 2
    df["LIPS"] = smma(df["MEDIAN"], lips_period).shift(lips_shift)

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
def plot_chart(df):

    fig = make_subplots(rows=1, cols=1)

    # -------------------------
    # Candlestick
    # -------------------------
    fig.add_trace(go.Candlestick(
        x=df["Date"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Candles"
    ))

    # -------------------------
    # EMA LINES
    # -------------------------
    fig.add_trace(go.Scatter(x=df["Date"], y=df["EMA_8"],
                             mode='lines', name='EMA 8'))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["EMA_14"],
                             mode='lines', name='EMA 14'))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["EMA_50"],
                             mode='lines', name='EMA 50'))

    # -------------------------
    # ALLIGATOR (LIPS)
    # -------------------------
    fig.add_trace(go.Scatter(x=df["Date"], y=df["LIPS"],
                             mode='lines', name='Alligator Lips'))

    # -------------------------
    # BUY SIGNAL
    # -------------------------
    buy = df[df["signal"] == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy["Date"], y=buy["Close"],
        mode='markers',
        marker=dict(symbol='triangle-up', size=10),
        name='BUY'
    ))

    # -------------------------
    # SELL SIGNAL
    # -------------------------
    sell = df[df["signal"] == "SELL"]
    fig.add_trace(go.Scatter(
        x=sell["Date"], y=sell["Close"],
        mode='markers',
        marker=dict(symbol='triangle-down', size=10),
        name='SELL'
    ))

    # -------------------------
    # EXIT BUY
    # -------------------------
    exit_buy = df[df["signal"] == "EXIT_BUY"]
    fig.add_trace(go.Scatter(
        x=exit_buy["Date"], y=exit_buy["Close"],
        mode='markers',
        marker=dict(symbol='x', size=8),
        name='EXIT BUY'
    ))

    # -------------------------
    # EXIT SELL
    # -------------------------
    exit_sell = df[df["signal"] == "EXIT_SELL"]
    fig.add_trace(go.Scatter(
        x=exit_sell["Date"], y=exit_sell["Close"],
        mode='markers',
        marker=dict(symbol='x', size=8),
        name='EXIT SELL'
    ))

    fig.update_layout(title="EMA + Alligator Strategy",
                      xaxis_title="Date",
                      yaxis_title="Price")

    fig.show()
    print("Chart plotted successfully")

# =========================
# MAIN
# =========================
def run():
    df = get_tv_data()
    df = add_features(df)
    df = ema_alligator_signals(df)
    process_transactions(df)
    plot_chart(df)


if __name__ == "__main__":
    run()