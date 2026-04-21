from ast import Param
from tvDatafeed import TvDatafeed, Interval
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd
import ta
from .telegram_bot import (
    TELEGRAM_ALERTS_ENABLED,
    build_signal_message,
    is_new_signal_alert,
    send_telegram_message,
)

def get_tv_data(symbol="BTCUSD", exchange="BITSTAMP",
                interval=Interval.in_5_minute, n_bars=2000):
    tv = TvDatafeed()
    df = tv.get_hist(symbol=symbol, exchange=exchange,
                     interval=interval, n_bars=n_bars)
    if df is None:
        print("Retrying data fetch...")
        df = tv.get_hist(symbol=symbol, exchange=exchange,
                         interval=interval, n_bars=n_bars)
    if df is None:
        raise Exception("TradingView data failed. Try again or change symbol.")
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

def smma(series, period):
    result = [None] * len(series)
    result[period - 1] = series[:period].mean()
    for i in range(period, len(series)):
        result[i] = (result[i - 1] * (period - 1) + series[i]) / period
    return pd.Series(result, index=series.index)

def add_features(df, params):
    df = df.copy()
    ema_8 = int(params.get("ema_8") or 8)
    ema_14 = int(params.get("ema_14") or 14)
    ema_50 = int(params.get("ema_50") or 50)
    lips_period = int(params.get("lips_period") or 5)
    lips_shift = int(params.get("lips_shift") or 3)
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

def ema_alligator_signals(df, params):
    df = df.copy()
    df["signal"] = None
    position = None
    entry_price = 0
    STOP_LOSS = float(params.get("stop_loss", 0.005))
    TARGET = float(params.get("target", 0.01))
    for i in range(1, len(df)):
        close = df["Close"].iloc[i]
        ema14 = df["EMA_14"].iloc[i]
        ema50 = df["EMA_50"].iloc[i]
        lips = df["LIPS"].iloc[i]
        rsi = df["RSI"].iloc[i]
        adx = df["ADX"].iloc[i]
        cross_up = df["EMA_CROSS_UP"].iloc[i]
        cross_down = df["EMA_CROSS_DOWN"].iloc[i]
        if pd.isna(lips) or pd.isna(rsi) or pd.isna(adx):
            continue
        if position is None:
            if cross_up and close > lips and close > ema50 and rsi > 55 and adx > 20:
                df.loc[i, "signal"] = "BUY"
                position = "BUY"
                entry_price = close
            elif cross_down and close < lips and close < ema50 and rsi < 45 and adx > 20:
                df.loc[i, "signal"] = "SELL"
                position = "SELL"
                entry_price = close
        elif position == "BUY":
            if close <= entry_price * (1 - STOP_LOSS) or close >= entry_price * (1 + TARGET) or close < ema14:
                df.loc[i, "signal"] = "EXIT_BUY"
                position = None
        elif position == "SELL":
            if close >= entry_price * (1 + STOP_LOSS) or close <= entry_price * (1 - TARGET) or close > ema14:
                df.loc[i, "signal"] = "EXIT_SELL"
                position = None
    return df

def trigger_signals(df, symbol="BTCUSD", enable_telegram_alerts=TELEGRAM_ALERTS_ENABLED):
    df = df.copy()
    df["trigger"] = None
    if df.empty or "signal" not in df.columns:
        return df

    valid_signals = {"BUY", "SELL", "EXIT_BUY", "EXIT_SELL"}
    last_index = df.index[-1]
    last_signal = df.at[last_index, "signal"]
    if pd.isna(last_signal) or last_signal not in valid_signals:
        return df

    df.at[last_index, "trigger"] = last_signal
    if not enable_telegram_alerts:
        return df

    last_price = float(df.at[last_index, "Close"]) if "Close" in df.columns else 0.0
    raw_time = df.at[last_index, "Date"] if "Date" in df.columns else pd.Timestamp.utcnow()
    candle_time = pd.to_datetime(raw_time).strftime("%Y-%m-%d %H:%M:%S")

    if is_new_signal_alert(symbol=symbol, signal=last_signal, candle_time=candle_time):
        message = build_signal_message(
            symbol=symbol,
            signal=last_signal,
            price=round(last_price, 2),
            candle_time=candle_time,
        )
        if send_telegram_message(message):
            print("📩 Telegram alert sent:", last_signal)
    return df

def process_transactions(df):
    trades = []
    position = None
    entry_price = 0
    for i in range(len(df)):
        signal = df["signal"].iloc[i]
        price = df["Close"].iloc[i]
        if signal == "BUY":
            position = "BUY"
            entry_price = price
        elif signal == "SELL":
            position = "SELL"
            entry_price = price
        elif signal == "EXIT_BUY" and position == "BUY":
            pnl = price - entry_price
            trades.append(pnl)
            position = None
        elif signal == "EXIT_SELL" and position == "SELL":
            pnl = entry_price - price
            trades.append(pnl)
            position = None
    trades = pd.Series(trades)
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
    print("\n===== STRATEGY SUMMARY =====")
    print(f"Total Trades : {total_trades}")
    print(f"Win Rate     : {round(win_rate, 2)} %")
    print(f"Total PnL    : {round(total_pnl, 2)}")
    print(f"Avg Win      : {round(avg_win, 2)}")
    print(f"Avg Loss     : {round(avg_loss, 2)}")

from plotly.subplots import make_subplots
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.graph_objects as go
def plot_chart(df):
    fig = make_subplots(rows=1, cols=1)
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
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["LIPS"],
        mode='lines', name='Alligator Lips',
        line=dict(color="yellow", width=1)
    ))
    buy = df[df["signal"] == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy["Date"], y=buy["Close"],
        mode='markers',
        marker=dict(symbol='triangle-up', size=10, color='#00ff9f'),
        name='BUY'
    ))
    sell = df[df["signal"] == "SELL"]
    fig.add_trace(go.Scatter(
        x=sell["Date"], y=sell["Close"],
        mode='markers',
        marker=dict(symbol='triangle-down', size=10, color='#ff4d4d'),
        name='SELL'
    ))
    exit_buy = df[df["signal"] == "EXIT_BUY"]
    fig.add_trace(go.Scatter(
        x=exit_buy["Date"], y=exit_buy["Close"],
        mode='markers',
        marker=dict(symbol='x', size=8, color='yellow'),
        name='EXIT BUY'
    ))
    exit_sell = df[df["signal"] == "EXIT_SELL"]
    fig.add_trace(go.Scatter(
        x=exit_sell["Date"], y=exit_sell["Close"],
        mode='markers',
        marker=dict(symbol='x', size=8, color='yellow'),
        name='EXIT SELL'
    ))
    fig.update_layout(
        title="EMA + Alligator Strategy",
        plot_bgcolor="#0b0f1a",
        paper_bgcolor="#0b0f1a",
        font=dict(color="white"),
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
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="white")
        )
    )
    return fig.to_html(full_html=False)

def generate_roi_data(df, investment):
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
            pct_change = (price - entry_price) / entry_price
            pnl = pct_change * investment   # ✅ FIX
            trades.append(pnl)
            times.append(time)
            position = None
        elif signal == "EXIT_SELL" and position == "SELL":
            pct_change = (entry_price - price) / entry_price
            pnl = pct_change * investment   # ✅ FIX
            trades.append(pnl)
            times.append(time)
            position = None
    if len(trades) == 0:
        return None
    trades = pd.Series(trades)
    cumulative = trades.cumsum()
    roi = (cumulative / investment) * 100  
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
    pos_roi = [x if x >= 0 else 0 for x in roi_values]
    neg_roi = [x if x < 0 else 0 for x in roi_values]
    fig.add_trace(go.Scatter(
        x=roi_data["times"],
        y=pos_roi,
        mode='lines',
        line=dict(color="#00ff9f", width=2),
        fill='tozeroy',
        fillcolor="rgba(0,255,159,0.15)",
        name="Profit ROI"
    ))
    fig.add_trace(go.Scatter(
        x=roi_data["times"],
        y=neg_roi,
        mode='lines',
        line=dict(color="#ff4d4d", width=2),
        fill='tozeroy',
        fillcolor="rgba(255,77,77,0.15)",
        name="Loss ROI"
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
            gridcolor="rgba(255,255,255,0.1)",
            zeroline=True,
            zerolinecolor="white"
        ),
        legend=dict(font=dict(color="white"))
    )
    return fig.to_html(full_html=False)

def generate_trade_log(df, investment):
    trades = []
    position = None
    entry_price = 0
    entry_time = None
    for i in range(len(df)):
        signal = df["signal"].iloc[i]
        price = df["Close"].iloc[i]
        time = df["Date"].iloc[i]
        if signal == "BUY":
            position = "BUY"
            entry_price = price
            entry_time = time
        elif signal == "SELL":
            position = "SELL"
            entry_price = price
            entry_time = time
        elif signal == "EXIT_BUY" and position == "BUY":
            pct_change = (price - entry_price) / entry_price
            pnl = pct_change * investment   # ✅ FIX
            duration_minutes = int((time - entry_time).total_seconds() // 60) if entry_time is not None else 0
            trades.append({
                "type": "BUY",
                "entry": round(entry_price, 2),
                "exit": round(price, 2),
                "pnl": round(pnl, 2),
                "entry_time": entry_time.strftime("%Y-%m-%d %H:%M") if entry_time is not None else "",
                "exit_time": time.strftime("%Y-%m-%d %H:%M"),
                "duration_min": duration_minutes
            })
            position = None
            entry_time = None
        elif signal == "EXIT_SELL" and position == "SELL":
            pct_change = (entry_price - price) / entry_price
            pnl = pct_change * investment   # ✅ FIX
            duration_minutes = int((time - entry_time).total_seconds() // 60) if entry_time is not None else 0
            trades.append({
                "type": "SELL",
                "entry": round(entry_price, 2),
                "exit": round(price, 2),
                "pnl": round(pnl, 2),
                "entry_time": entry_time.strftime("%Y-%m-%d %H:%M") if entry_time is not None else "",
                "exit_time": time.strftime("%Y-%m-%d %H:%M"),
                "duration_min": duration_minutes
            })
            position = None
            entry_time = None
    return trades


def _avg_duration_text(trades):
    if not trades:
        return "0m"
    avg_min = int(sum(t.get("duration_min", 0) for t in trades) / len(trades))
    hours = avg_min // 60
    minutes = avg_min % 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def build_trade_stats(trades_list):
    buy_trades = [t for t in trades_list if t.get("type") == "BUY"]
    sell_trades = [t for t in trades_list if t.get("type") == "SELL"]

    return {
        "total_signals": len(trades_list),
        "buy_signals": len(buy_trades),
        "sell_signals": len(sell_trades),
        "buy_strategy": {
            "runs": len(buy_trades),
            "avg_price": round(sum(t.get("entry", 0) for t in buy_trades) / len(buy_trades), 2) if buy_trades else 0,
            "duration": _avg_duration_text(buy_trades),
            "pnl": round(sum(t.get("pnl", 0) for t in buy_trades), 2),
        },
        "sell_strategy": {
            "runs": len(sell_trades),
            "avg_price": round(sum(t.get("entry", 0) for t in sell_trades) / len(sell_trades), 2) if sell_trades else 0,
            "duration": _avg_duration_text(sell_trades),
            "pnl": round(sum(t.get("pnl", 0) for t in sell_trades), 2),
        }
    }


def plot_profitloss_graph(trades_list):
    if not trades_list:
        return None
    x_values = [f"T{i + 1}" for i in range(len(trades_list))]
    y_values = [t.get("pnl", 0) for t in trades_list]
    colors = ["#84cc16" if pnl >= 0 else "#f87171" for pnl in y_values]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x_values,
        y=y_values,
        marker_color=colors,
        name="Trade PnL ($)"
    ))
    fig.update_layout(
        title="Profitloss",
        plot_bgcolor="#0b0f1a",
        paper_bgcolor="#0b0f1a",
        font=dict(color="white"),
        xaxis=dict(title="Trades", showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(title="PnL ($)", showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
        legend=dict(font=dict(color="white"))
    )
    return fig.to_html(full_html=False)

def run_backtest(params=None, send_alerts=False):

    if params is None:
        params = {}
    investment = float(params.get("investment") or 1000) 
    symbol = params.get("symbol") or "BTCUSD"
    df = get_tv_data()
    df = add_features(df, params)
    df = ema_alligator_signals(df, params)
    if send_alerts:
        df = trigger_signals(
            df,
            symbol=symbol,
            enable_telegram_alerts=params.get("enable_telegram_alerts", TELEGRAM_ALERTS_ENABLED),
        )
    chart_html = plot_chart(df)
    roi_data = generate_roi_data(df, investment)   
    roi_chart = plot_roi_graph(roi_data) if roi_data else None
    trades_list = generate_trade_log(df, investment)  
    stats = build_trade_stats(trades_list)
    profitloss_chart = plot_profitloss_graph(trades_list)
    wins = [t for t in trades_list if t["pnl"] > 0]
    total_trades = len(trades_list)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
   
    return {
        "strategy": "EMA Alligator Strategy",
        "chart": chart_html,
        "roi_chart": roi_chart,
        "roi_overall": roi_data["roi_overall"] if roi_data else 0,
        "total_pnl": roi_data["total_pnl"] if roi_data else 0,
        "total_trades": roi_data["total_trades"] if roi_data else 0,
        "trades": trades_list,
        "win_rate": round(win_rate, 2),
        "profitloss_chart": profitloss_chart,
        "total_signals": stats["total_signals"],
        "buy_signals": stats["buy_signals"],
        "sell_signals": stats["sell_signals"],
        "buy_strategy": stats["buy_strategy"],
        "sell_strategy": stats["sell_strategy"],
    }

def process_strategy(params=None):
    if params is None:
        params = {}
    symbol = params.get("symbol") or "BTCUSD"
    df = get_tv_data(symbol=symbol)
    df = add_features(df, params)
    df = ema_alligator_signals(df, params)
    df = trigger_signals(
        df,
        symbol=symbol,
        enable_telegram_alerts=params.get("enable_telegram_alerts", TELEGRAM_ALERTS_ENABLED),
    )
if __name__ == "__main__":
    run_backtest()

