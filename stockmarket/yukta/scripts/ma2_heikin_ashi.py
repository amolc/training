
from numpy.linalg import eig
from tvDatafeed import TvDatafeed, Interval
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd
import pygsheets
from yukta.services import save_df_to_db

# GET DATA
def get_tv_data(symbol="BTCUSD", exchange="COINBASE",
                interval=Interval.in_5_minute, n_bars=2000):
    try:
        print(f"Fetching data for {symbol} from {exchange} with interval {interval}...")
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
        df["Stock"]=symbol
        df = df.sort_values("Date")

        return df

    except Exception as e:
        print(f"[ERROR] Data Fetch Failed: {e}")
        return None
    
# HEIKIN ASHI
def convert_to_heikin_ashi(df):
    try:
        df = df.copy()

        df["HA_Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4

        df["HA_Open"] = 0.0
        for i in range(len(df)):
            if i == 0:
                df.loc[i, "HA_Open"] = (df.loc[i, "Open"] + df.loc[i, "Close"]) / 2
            else:
                df.loc[i, "HA_Open"] = (df.loc[i-1, "HA_Open"] + df.loc[i-1, "HA_Close"]) / 2

        df["HA_High"] = df[["High", "HA_Open", "HA_Close"]].max(axis=1)
        df["HA_Low"] = df[["Low", "HA_Open", "HA_Close"]].min(axis=1)

        print("Heikin Ashi conversion complete.")
        return df
    
    except Exception as e:
        print(f"[ERROR] Heikin Ashi Conversion Failed: {e}")
        return df



    


# EMA
def add_features(df):
    try:
        df = df.copy()

        df["EMA_HIGH"] = df["High"].ewm(span=20, adjust=False).mean()
        df["EMA_LOW"] = df["Low"].ewm(span=20, adjust=False).mean()

        print("EMA calculation complete.")
        return df

    except Exception as e:
        print(f"[ERROR] EMA Calculation Failed: {e}")
        return df


# CROSSOVER
def generate_signals(df):
    try:
        print("Generating trading signals based on strategy rules...")
        df = df.copy()

        df["signal"] = None
        df["position"] = None

        position = None  # None / BUY / SELL
        entry_price = 0

        stop_loss = 0.005   #0.5% stop loss
        target_profit = 0.01  #1% target profit

        for i in range(len(df)):
            row = df.iloc[i]

            close = row["HA_Close"]   # using Heikin Ashi close
            ema_high = row["EMA_HIGH"]
            ema_low = row["EMA_LOW"]
            time = row["Date"].strftime("%Y-%m-%d %H:%M")


            # ======================
            # NO POSITION
            # ======================
            if position is None:
                #generate signal stop loss of 0.005

                # BUY ENTRY
                if close > ema_high:
                    df.loc[i, "signal"] = "BUY"
                    position = "BUY"
                    entry_price = close
                    print(f"{time} → BUY at {round(close, 2)}")


                # SELL ENTRY
                elif close < ema_low:
                    df.loc[i, "signal"] = "SELL"
                    position = "SELL"
                    entry_price = close
                    print(f"{time} → SELL at {round(close, 2)}")


            # ======================
            # BUY POSITION
            # ======================
            elif position == "BUY":

                stop_loss_price = entry_price * (1 - stop_loss)  # stop loss price is 0.005 below entry price
                target_profit_price = entry_price * (1 + target_profit)  # target profit price is 1% above entry price

                #STOP LOSS HIT
                if close <= stop_loss_price:
                    df.loc[i, "signal"] = "STOP_LOSS_BUY"
                    position = None

                    print(f"{time} → STOP LOSS BUY at {round(close, 2)}")


                #TARGET HIT
                elif close >= target_profit_price:
                    df.loc[i, "signal"] = "TARGET_PROFIT_BUY"
                    position = None

                    print(f"{time} → TARGET BUY at {round(close, 2)}")


                # EXIT BUY
                elif close < ema_high:
                    #close when profit is 0.01%
                        df.loc[i, "signal"] = "EXIT_BUY"
                        position = None
                        print(f"{time} → EXIT BUY at {round(close, 2)}")


            # ======================
            # SELL POSITION
            # ======================
            elif position == "SELL":

                stop_loss_price = entry_price * (1 + stop_loss)  # stop loss price is 0.005 above entry price
                target_profit_price = entry_price * (1 - target_profit)  # target profit price is 1% below entry price

                #STOP LOSS HIT
                if close >= stop_loss_price:
                    df.loc[i, "signal"] = "STOP_LOSS_SELL"
                    position = None
                    print(f"{time} → STOP LOSS SELL at {round(close, 2)}")


                #TARGET HIT
                elif close <= target_profit_price:
                    df.loc[i, "signal"] = "TARGET_PROFIT_SELL"
                    position = None
                    print(f"{time} → TARGET SELL at {round(close, 2)}")


                # EXIT SELL
                elif close > ema_low:
                    df.loc[i, "signal"] = "EXIT_SELL"
                    position = None
                    print(f"{time} → EXIT SELL at {round(close, 2)}")


            df.loc[i, "position"] = position

        save_df_to_db(df)
        return df

    except Exception as e:
        print(f"[ERROR] Signal Generation Failed: {e}")
        return df
    

# TRADE SUMMARY
def generate_trade_summary(df):
    try:
        trades = []
        position = None   # None / BUY / SELL
        entry_price = 0
        entry_time = None

        for i in range(len(df)):
            row = df.iloc[i]

            signal = row["signal"]
            price = row["HA_Close"]   # using Heikin Ashi close
            time = row["Date"]

            # ======================
            # ENTRY
            # ======================
            if signal == "BUY" and position is None:
                position = "BUY"
                entry_price = price
                entry_time = time
                

            elif signal == "SELL" and position is None:
                position = "SELL"
                entry_price = price
                entry_time = time
                

            # ======================
            # EXIT BUY
            # ======================
            elif signal in ["EXIT_BUY", "TARGET_PROFIT_BUY", "STOP_LOSS_BUY"] and position == "BUY":
                exit_price = price
                exit_time = time

                profit = exit_price - entry_price

                #EXIT TYPE
                if signal == "STOP_LOSS_BUY":
                    exit_type = "STOP_LOSS"
                elif signal in ["TARGET_PROFIT_BUY"]:   
                    exit_type = "TARGET_PROFIT"
                else:
                    exit_type = "TREND EXIT"

                

                trades.append({
                    "Type": "BUY",
                    "Entry Time": entry_time,
                    "Exit Time": exit_time,
                    "Entry Price": entry_price,
                    "Exit Price": exit_price,
                    "Profit/Loss": profit,
                    "Exit Type": exit_type
                })

                position = None

            # ======================
            # EXIT SELL
            # ======================
            elif signal in ["EXIT_SELL", "TARGET_PROFIT_SELL", "STOP_LOSS_SELL"] and position == "SELL":
                exit_price = price
                exit_time = time

                profit = entry_price - exit_price  # IMPORTANT (reverse for SELL)

                #EXIT TYPE
                if signal == "STOP_LOSS_SELL":
                    exit_type = "STOP_LOSS"
                elif signal in ["TARGET_PROFIT_SELL"]:      
                    exit_type = "TARGET_PROFIT"
                else:
                    exit_type = "TREND EXIT"

               
                trades.append({
                    "Type": "SELL",
                    "Entry Time": entry_time,
                    "Exit Time": exit_time,
                    "Entry Price": entry_price,
                    "Exit Price": exit_price,
                    "Profit/Loss": profit,
                    "Exit Type": exit_type
                })

                position = None

        # ======================
        # HANDLE OPEN TRADE
        # ======================
        if position is not None:
            last_row = df.iloc[-1]
            exit_price = last_row["HA_Close"]
            exit_time = last_row["Date"]

            if position == "BUY":
                profit = exit_price - entry_price
            else:
                profit = entry_price - exit_price

            trades.append({
                "Type": position,
                "Entry Time": entry_time,
                "Exit Time": exit_time,
                "Entry Price": entry_price,
                "Exit Price": exit_price,
                "Profit/Loss": profit,
                "Exit Type": "TREND EXIT"
            })

        # ======================
        # SUMMARY STATS
        # ======================
        total_trades = len(trades)
        wins = sum(1 for t in trades if t["Profit/Loss"] > 0)
        losses = sum(1 for t in trades if t["Profit/Loss"] <= 0)
        total_profit = sum(t["Profit/Loss"] for t in trades)

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # BUY / SELL breakdown
        buy_trades = [t for t in trades if t["Type"] == "BUY"]
        sell_trades = [t for t in trades if t["Type"] == "SELL"]

        summary_df = pd.DataFrame([{
            "Total Trades": total_trades,
            "Wins": wins,
            "Losses": losses,
            "Win Rate (%)": round(win_rate, 2),
            "Total Profit": round(total_profit, 2),
            "Buy Trades": len(buy_trades),
            "Sell Trades": len(sell_trades)
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

        # Extra stats
        if not trades_df.empty:
            avg_profit = trades_df["Profit/Loss"].mean()
            max_profit = trades_df["Profit/Loss"].max()
            max_loss = trades_df["Profit/Loss"].min()

            print("\n📌 EXTRA STATS")
            print(f"Average Profit per Trade: {round(avg_profit, 2)}")
            print(f"Max Profit: {round(max_profit, 2)}")
            print(f"Max Loss: {round(max_loss, 2)}")

    # ======================
            # EXIT TYPE ANALYSIS
            # ======================
            print("\n📊 EXIT TYPE ANALYSIS")

            exit_counts = trades_df["Exit Type"].value_counts()
            print(exit_counts)

            # ======================
            # WIN RATE BY TYPE
            # ======================
            print("\n📈 WIN RATE BY EXIT TYPE")

            for exit_type in trades_df["Exit Type"].unique():
                subset = trades_df[trades_df["Exit Type"] == exit_type]

                wins = len(subset[subset["Profit/Loss"] > 0])
                total = len(subset)

                win_rate = (wins / total * 100) if total > 0 else 0

                print(f"{exit_type} → {round(win_rate, 2)}% win rate")

            # ======================
            # PROFIT BY TYPE
            # ======================
            print("\n💰 PROFIT BY EXIT TYPE")

            profit_by_type = trades_df.groupby("Exit Type")["Profit/Loss"].sum()

            print(profit_by_type)

    except Exception as e:
        print(f"[ERROR] Printing Failed: {e}")


# UPLOAD TO GOOGLE SHEETS
def save_to_google_sheet(df, trades, summary):
    try:
        print("Connecting to Google Sheets...")

        gc = pygsheets.authorize(service_file='credentials.json')
        sh = gc.open("Reliance Trading Data")

        # =========================
        # SHEET 0 → FULL DATA
        # =========================
        wks1 = sh[0]
        wks1.clear()

        full_df = df.copy()

        wks1.set_dataframe(full_df, (1, 1))

        # =========================
        # SHEET 1 → TRADES + SUMMARY
        # =========================
        # Ensure sheet exists
        if len(sh.worksheets()) < 3:
            sh.add_worksheet(f"Sheet{len(sh.worksheets())+1}")

        wks2 = sh[1]
        wks2.clear()

        trades_df = pd.DataFrame(trades)

        # ---- WRITE TRADES ----
        if not trades_df.empty:
            wks2.update_value("A1", "TRADES")
            wks2.set_dataframe(trades_df, (2, 1))
            start_row = len(trades_df) + 4
        else:
            start_row = 2

        # SHEET 2 - WRITE SUMMARY ----
        wks3 = sh[2]
        wks3.clear()
        wks3.set_dataframe(summary, (1, 1))

        if summary is not None:
            wks3.update_value("A1", "SUMMARY")
            wks3.set_dataframe(summary, (2, 1))
        else:
            wks3.update_value("A1", "NO SUMMARY")

        print("[SUCCESS] Data + Trades + Summary saved to Google Sheets")

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
        fig = make_subplots(rows=1, cols=1)

        fig.add_trace(go.Candlestick(
            x=df["Date"],
            open=df['HA_Open'],
            high=df['HA_High'],
            low=df['HA_Low'],
            close=df['HA_Close'],
            name="Heikin Ashi Price"
        ))

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df["EMA_HIGH"],
            line=dict(color="green",width=4),
            name="EMA_HIGH"
        ))

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df["EMA_LOW"],
            line=dict(color="red",width=4),
            name="EMA_LOW"
        ))

      
        # Buy signals
        buy = df[df["signal"] == "BUY"]
        fig.add_trace(go.Scatter(
            x=buy["Date"],
            y=buy["HA_Close"],
            mode="markers",
            name="BUY",
            marker=dict(symbol="triangle-up",size=16,color="lime", line=dict(color="white", width=2))
        ))

        # Sell signals
        sell = df[df["signal"] == "SELL"]
        fig.add_trace(go.Scatter(
            x=sell["Date"],
            y=sell["HA_Close"],
            mode="markers",
            name="SELL",
            marker=dict(symbol="triangle-down",size=16,color="magenta",line=dict(color="white", width=2))
        ))

        #EXIT BUY
        exit_buy = df[df["signal"] == "EXIT_BUY"]
        fig.add_trace(go.Scatter(
            x=exit_buy["Date"],
            y=exit_buy["HA_Close"],
            mode="markers",
            name="EXIT BUY",
            marker=dict(symbol="x", size=12, color="cyan",line=dict(width=2))
        ))


        #EXIT SELL
        exit_sell = df[df["signal"] == "EXIT_SELL"]
        fig.add_trace(go.Scatter(
            x=exit_sell["Date"],
            y=exit_sell["HA_Close"],
            mode="markers",
            name="EXIT SELL",
            marker=dict(symbol="circle", size=10, color="yellow",line=dict(width=2))
        ))


        fig.update_layout(
            title="EMA + Heikin Ashi Strategy",
            template="plotly_dark"
        )


        fig.show()
        print("[SUCCESS] Plotting completed")



    except Exception as e:
        print(f"[ERROR] Plotting Failed: {e}")



#  MAIN RUN

def run():
    try:
        df = get_tv_data()
        
        df = convert_to_heikin_ashi(df)

        if df is None:
            print("[STOP] No data available")
            return

        print("Data loaded successfully.")

        
        df = add_features(df)
        df = generate_signals(df)
        save_df_to_db(df)

        save_data(df)
        plot(df)

        trades, summary = generate_trade_summary(df)        
        print_trade_summary(trades, summary)
        save_to_google_sheet(df, trades, summary)

        print("[SUCCESS] Program executed successfully")

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")


# RUN
if __name__ == "__main__":
    run()
