
from tvDatafeed import TvDatafeed, Interval
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd
import pygsheets

# GET DATA
def get_tv_data(symbol="BTCUSD", exchange="COINBASE",
                interval=Interval.in_5_minute, n_bars=1000):
    try:
        tv = TvDatafeed()

        df = tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            n_bars=n_bars
        )

        

        if df is None or df.empty:
            raise ValueError("No data received")

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
        df = df.sort_values("Date")

        return df

    except Exception as e:
        print(f"[ERROR] Data Fetch Failed: {e}")
        return None


# ATR
def calculate_atr(df, period=14):
    try:
        df = df.copy()

        df["Prev_Close"] = df["Close"].shift(1)

        df["True_Range"] = df.apply(
            lambda x: max(
                x["High"] - x["Low"],
                abs(x["High"] - x["Prev_Close"]),
                abs(x["Low"] - x["Prev_Close"])
            ),
            axis=1
        )

        df["ATR"] = df["True_Range"].rolling(period).mean()

        return df

    except Exception as e:
        print(f"[ERROR] ATR Calculation Failed: {e}")
        return df


# EMA
def add_features(df):
    try:
        df = df.copy()

        df["EMA1"] = df["Close"].ewm(span=21, adjust=False).mean()
        df["EMA2"] = df["Close"].ewm(span=50, adjust=False).mean()

        return df

    except Exception as e:
        print(f"[ERROR] EMA Calculation Failed: {e}")
        return df


# CROSSOVER
def generate_signals(df):
    try:
        df = df.copy()

        df["prev_EMA1"] = df["EMA1"].shift(1)
        df["prev_EMA2"] = df["EMA2"].shift(1)

        df["buy_signal"] = (
            (df["EMA1"] > df["EMA2"]) &
            (df["prev_EMA1"] <= df["prev_EMA2"])
        )

        df["sell_signal"] = (
            (df["EMA1"] < df["EMA2"]) &
            (df["prev_EMA1"] >= df["prev_EMA2"])        
        )

        return df

    except Exception as e:
        print(f"[ERROR] Signal Generation Failed: {e}")
        return df


# TRADE SUMMARY
def generate_trade_summary(df):
    try:
        trades = []
        position = None   # None / "BUY"
        entry_price = 0
        entry_time = None

        for i in range(len(df)):
            row = df.iloc[i]

            # BUY
            if row["buy_signal"] and position is None:
                position = "BUY"
                entry_price = row["Close"]
                entry_time = row["Date"]

            # SELL
            elif row["sell_signal"] and position == "BUY":
                exit_price = row["Close"]
                exit_time = row["Date"]

                profit = exit_price - entry_price

                trades.append({
                    "Entry Time": entry_time,
                    "Exit Time": exit_time,
                    "Entry Price": entry_price,
                    "Exit Price": exit_price,
                    "Profit/Loss": profit
                })

                position = None
        
        #TO HANDLE OPEN POSITIONS
        if position == "BUY":
            last_row = df.iloc[-1]
            exit_price = last_row["Close"]
            exit_time = last_row["Date"]

            profit = exit_price - entry_price

            trades.append({
                "Entry Time": entry_time,
                "Exit Time": exit_time,
                "Entry Price": entry_price,
                "Exit Price": exit_price,
                "Profit/Loss": profit
            })

        # SUMMARY
        total_trades = len(trades)
        wins = sum(1 for t in trades if t["Profit/Loss"] > 0)
        losses = sum(1 for t in trades if t["Profit/Loss"] <= 0)
        total_profit = sum(t["Profit/Loss"] for t in trades)

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # ✅ Convert to table format
        summary_df = pd.DataFrame([{
            "Total Trades": total_trades,
            "Wins": wins,
            "Losses": losses,
            "Win Rate (%)": round(win_rate, 2),
            "Total Profit": round(total_profit, 2)
        }])

        return trades, summary_df

    except Exception as e:
        print(f"[ERROR] Trade Summary Failed: {e}")
        return None, None
    
def print_trade_summary(trades, summary):
    try:
        import pandas as pd

        # ✅ Convert trades list → DataFrame
        trades_df = pd.DataFrame(trades)

        print("\n========= TRADE TABLE =========")
        print(trades_df)

        print("\n========= SUMMARY =========")
        print(summary)

    except Exception as e:
        print(f"[ERROR] Printing Failed: {e}")


# UPLOAD TO GOOGLE SHEETS
def save_to_google_sheet(df):
    try:
        gc = pygsheets.authorize(service_file='credentials.json')
        sh = gc.open("Reliance Trading Data")

        # Sheet 1 → Main Data
        wks1 = sh[0]
        wks1.clear()

        # Keep only useful columns
        clean_df = df[[
            "Date", "Open", "High", "Low", "Close",
            "EMA1", "EMA2", "ATR",
            "buy_signal", "sell_signal"
        ]].copy()

        clean_df.rename(columns={
            "buy_signal": "Buy",
            "sell_signal": "Sell"
        }, inplace=True)

        wks1.set_dataframe(clean_df, (1, 1))

        print("[SUCCESS] Data saved to Google Sheets")

    except Exception as e:
        print(f"[ERROR] Google Sheets upload failed: {e}")


# SAVE DATA

def save_data(df, filename="reliance_data.csv"):
    try:
        df.to_csv(filename, index=False)
        print("[SUCCESS] Data saved")

    except Exception as e:
        print(f"[ERROR] Saving Failed: {e}")



# PLOT

def plot(df):
    try:
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3]
        )

        fig.add_trace(go.Candlestick(
            x=df["Date"],
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name="Price"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df["EMA1"],
            mode="lines",
            name="EMA 21"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df["EMA2"],
            mode="lines",
            name="EMA 50"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df['ATR'],
            mode="lines",
            name="ATR"
        ), row=2, col=1)

        # Buy signals
        buy = df[df["buy_signal"]]
        fig.add_trace(go.Scatter(
            x=buy["Date"],
            y=buy["Close"],
            mode="markers",
            name="Buy",
            marker=dict(symbol="triangle-up", size=12)
        ), row=1, col=1)

        # Sell signals
        sell = df[df["sell_signal"]]
        fig.add_trace(go.Scatter(
            x=sell["Date"],
            y=sell["Close"],
            mode="markers",
            name="Sell",
            marker=dict(symbol="triangle-down", size=12)
        ), row=1, col=1)

        fig.update_layout(
            title="EMA Crossover + ATR Strategy",
            template="plotly_dark"
        )

        fig.update_xaxes(
            rangebreaks=[
                dict(bounds=["sat", "mon"]),  # remove weekends
                dict(bounds=[15.5, 9.15], pattern="hour")  # remove non-market hours
            ]
        )

        fig.show()

    except Exception as e:
        print(f"[ERROR] Plotting Failed: {e}")



#  MAIN RUN

def run():
    try:
        df = get_tv_data()

        if df is None:
            print("[STOP] No data available")
            return

        print("Data loaded")

        df = calculate_atr(df)
        df = add_features(df)
        df = generate_signals(df)

        save_data(df)
        plot(df )

        trades, summary = generate_trade_summary(df)        
        print_trade_summary(trades, summary)
        save_to_google_sheet(df)

        print("[SUCCESS] Program executed successfully")

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")


# RUN
if __name__ == "__main__":
    run()
