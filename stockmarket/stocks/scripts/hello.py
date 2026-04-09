import yfinance as yf
import pandas as pd
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots


def flatten_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        if (
            data.columns.nlevels == 2
            and data.columns.get_level_values(1).nunique() == 1
        ):
            data.columns = data.columns.get_level_values(0)
        else:
            data.columns = [
                f"{price}_{ticker}"
                for price, ticker in data.columns.to_flat_index()
            ]
    data.columns.name = None
    data.index = pd.to_datetime(data.index)
    data.index.name = "Datetime"
    return data


def getdata() -> pd.DataFrame:
    print("hello world")
    ticker = "RELIANCE.NS"
    data = yf.download(
        ticker,
        start="2023-01-01",
        end="2024-01-01",
        interval="1d",
    )
    if data is None:
        return pd.DataFrame()
    data = flatten_ohlcv(data)
    return data


def multiplestocks():
    tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    data = yf.download(tickers, period="1mo", interval="1d")
    if data is None:
        print(pd.DataFrame())
        return
    data = flatten_ohlcv(data)
    print(data)


def addfeatures(df):
    df = df.copy()
    df["ma9"] = df["Close"].rolling(9).mean()
    df["ma21"] = df["Close"].rolling(21).mean()
    return df


def crossover(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    prev_ma9 = df["ma9"].shift(1)
    prev_ma21 = df["ma21"].shift(1)
    df["upcrossover"] = (df["ma9"] > df["ma21"]) & (prev_ma9 <= prev_ma21)
    df["downcrossover"] = (df["ma9"] < df["ma21"]) & (prev_ma9 >= prev_ma21)
    return df


def calculateprofitloss(df: pd.DataFrame) -> dict:
    required = {"Close", "upcrossover", "downcrossover"}
    if not required.issubset(df.columns):
        missing = sorted(required - set(df.columns))
        raise ValueError(f"Missing required columns: {missing}")

    index_name = df.index.name or "Datetime"
    rows = df.reset_index().to_dict("records")
    in_position = False
    buy_price = 0.0
    buy_time: Any = None
    trades = []

    for row in rows:
        timestamp = row.get(index_name)
        close_raw = row.get("Close")
        try:
            close_value = float(str(close_raw))
        except (TypeError, ValueError):
            continue
        is_up = bool(row.get("upcrossover", False))
        is_down = bool(row.get("downcrossover", False))

        if is_up and not in_position:
            buy_price = close_value
            buy_time = timestamp
            in_position = True
            continue

        if is_down and in_position:
            sell_price = close_value
            pnl = sell_price - buy_price
            pnl_pct = (pnl / buy_price) * 100 if buy_price else 0.0
            trades.append(
                {
                    "buy_time": buy_time,
                    "buy_price": buy_price,
                    "sell_time": timestamp,
                    "sell_price": sell_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "result": "win" if pnl > 0 else "loss",
                }
            )
            in_position = False

    if in_position and buy_time is not None and rows:
        last_row = rows[-1]
        last_time = last_row.get(index_name)
        last_close = last_row.get("Close")
        try:
            last_price = float(str(last_close))
        except (TypeError, ValueError):
            last_price = buy_price
        pnl = last_price - buy_price
        pnl_pct = (pnl / buy_price) * 100 if buy_price else 0.0
        trades.append(
            {
                "buy_time": buy_time,
                "buy_price": buy_price,
                "sell_time": last_time,
                "sell_price": last_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "result": "win" if pnl > 0 else "loss",
            }
        )

    trades_df = pd.DataFrame(trades)
    total_trades = len(trades)
    total_pnl = (
        float(sum(float(trade["pnl"]) for trade in trades))
        if trades
        else 0.0
    )
    wins = sum(1 for trade in trades if float(trade["pnl"]) > 0)
    winrate = (wins / total_trades) * 100 if total_trades else 0.0

    summary = {
        "total_trades": total_trades,
        "wins": wins,
        "losses": total_trades - wins,
        "winrate": winrate,
        "total_pnl": total_pnl,
    }
    return {"trades": trades_df, "summary": summary}


def buyandhold(df: pd.DataFrame) -> dict:
    if "Close" not in df.columns:
        raise ValueError("Close column is required for buy-and-hold.")
    default_result = {
        "buy_time": None,
        "sell_time": None,
        "buy_price": 0.0,
        "sell_price": 0.0,
        "pnl": 0.0,
        "pnl_pct": 0.0,
    }
    if df.empty:
        return default_result

    index_name = df.index.name or "Datetime"
    rows = df.reset_index().to_dict("records")
    valid_points = []
    for row in rows:
        close_raw = row.get("Close")
        try:
            close_value = float(str(close_raw))
        except (TypeError, ValueError):
            continue
        valid_points.append((row.get(index_name), close_value))

    if not valid_points:
        return default_result

    buy_time, buy_price = valid_points[0]
    sell_time, sell_price = valid_points[-1]
    pnl = sell_price - buy_price
    pnl_pct = (pnl / buy_price) * 100 if buy_price else 0.0
    return {
        "buy_time": buy_time,
        "sell_time": sell_time,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


def createchart(df: pd.DataFrame):
    if df.empty:
        raise ValueError("Cannot create chart from an empty dataframe.")

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
    )

    if "Close" in df.columns:
        figure.add_trace(
            go.Scatter(
                x=df.index,
                y=df["Close"],
                mode="lines",
                name="Close",
                line={"color": "black", "width": 2},
            ),
            row=1,
            col=1,
        )
    else:
        first_col = df.select_dtypes(include="number").columns[0]
        figure.add_trace(
            go.Scatter(
                x=df.index,
                y=df[first_col],
                mode="lines",
                name=str(first_col),
                line={"color": "black", "width": 2},
            ),
            row=1,
            col=1,
        )

    if "ma9" in df.columns:
        figure.add_trace(
            go.Scatter(
                x=df.index,
                y=df["ma9"],
                mode="lines",
                name="MA 9",
                line={"width": 1.5},
            ),
            row=1,
            col=1,
        )

    if "ma21" in df.columns:
        figure.add_trace(
            go.Scatter(
                x=df.index,
                y=df["ma21"],
                mode="lines",
                name="MA 21",
                line={"width": 1.5},
            ),
            row=1,
            col=1,
        )

    if "upcrossover" in df.columns:
        up = df[df["upcrossover"]]
        if not up.empty:
            figure.add_trace(
                go.Scatter(
                    x=up.index,
                    y=up["Close"],
                    mode="markers",
                    name="Up Crossover",
                    marker={
                        "symbol": "triangle-up",
                        "size": 10,
                        "color": "green",
                    },
                ),
                row=1,
                col=1,
            )

    if "downcrossover" in df.columns:
        down = df[df["downcrossover"]]
        if not down.empty:
            figure.add_trace(
                go.Scatter(
                    x=down.index,
                    y=down["Close"],
                    mode="markers",
                    name="Down Crossover",
                    marker={
                        "symbol": "triangle-down",
                        "size": 10,
                        "color": "red",
                    },
                ),
                row=1,
                col=1,
            )

    if "Volume" in df.columns:
        figure.add_trace(
            go.Bar(x=df.index, y=df["Volume"], name="Volume"),
            row=2,
            col=1,
        )

    figure.update_layout(
        title="Stock Chart",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
    )
    output_path = Path(__file__).resolve().parent / "stock_chart.html"
    figure.write_html(str(output_path), auto_open=True)
    pio.renderers.default = "browser"
    figure.show()
    print(f"chart saved at: {output_path}")
    return figure


def run():
    df = getdata()
    df = addfeatures(df)
    df = crossover(df)
    report = calculateprofitloss(df)
    hold_report = buyandhold(df)
    print(report["trades"])
    print(report["summary"])
    print(hold_report)
    createchart(df)
