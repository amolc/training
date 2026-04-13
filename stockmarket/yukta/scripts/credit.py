import pygsheets
import yfinance as yf
from plotly.subplots import make_subplots
import plotly.graph_objects as go

print("Wroking")
def get_data():
    reliance=yf.Ticker("RELIANCE.NS")
    df=reliance.history(period="1y",interval="1d")
    return df

data=get_data()

#ATR=rolling average of the largest price movement per day
def calculate_atr(data, period=14):
    df=data.copy()
    #previous close
    df["Prev_Close"]=df["Close"].shift(1)
    #True range
    df["True_Range"]=df[["High","Low","Prev_Close"]].apply(
        lambda x: max(x["High"]-x["Low"],abs(x["High"]-x["Prev_Close"]),
                      abs(x["Low"]-x["Prev_Close"])),
                      axis=1
                      )
    #ATR (Rolling mean)
    df["ATR"]=df["True_Range"].rolling(period).mean()

    return df

data=calculate_atr(data)
print("ATR calculated successfully")

def add_ema(data):
    df=data.copy()

    #exponential moving average of 9 and 13
    #ewm=exponential weighted moving
    df["EMA_9"]=df["Close"].ewm(span=9,adjust=False).mean()
    df["EMA_13"]=df["Close"].ewm(span=13,adjust=False).mean()
    return df

data=add_ema(data)
print("EMA calculated successfully")

def add_crossover(data):
    df=data.copy()

    #Create previous EMA columns
    df["prev_EMA9"] = df["EMA_9"].shift(1)
    df["prev_EMA13"] = df["EMA_13"].shift(1)
    #Buy signal
    df["buy_signal"]=(df["EMA_9"]>df["EMA_13"])&(df["prev_EMA9"]<=df["prev_EMA13"])
    #Sell signal
    df["sell_signal"]=(df["EMA_9"]<df["EMA_13"])&(df["prev_EMA9"]>=df["prev_EMA13"])
    return df

data=add_crossover(data)
print("Crossover signals calculated successfully")

print(data.head())

def save_data():
    data.to_csv("reliance_data.csv")
    print("Data saved successfully")

save_data()



def plot(data):
    fig=make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.2,
        row_heights=[0.7,0.3]
        )

    #Candlestick
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        name="Price"
        ), row=1, col=1)
    
    #EMA_9
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data["EMA_9"],
        mode="lines",
        name="EMA_9",
        line=dict(color="cyan",width=2)
        ),row=1, col=1)
    
    #EMA_13
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data["EMA_13"],
        mode="lines",
        name="EMA_13",
        line=dict(color="magenta",width=2)
    ),row=1, col=1)
    
    #ATR
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['ATR'],
        mode="lines",
        name="ATR",
        line=dict(color="brown",width=2)
        ), row=2, col=1)
    
    sell=data[data["sell_signal"]]
    fig.add_trace(go.Scatter(
        x=sell.index,
        y=sell["Close"],
        mode="markers",
        name="Sell",
        marker=dict(symbol="triangle-down", color="lime", size=15)
    ), row=1, col=1)

    buy=data[data["buy_signal"]]
    fig.add_trace(go.Scatter(
        x=buy.index,
        y=buy["Close"],
        mode="markers",
        name="Buy",
        marker=dict(symbol="triangle-up", color="blue", size=15)
    ), row=1, col=1)
   
    fig.update_layout(
        title="Reliance Price + ATR +EMA + Crossover signals",
        template="plotly_dark"
    )

    fig.show()
    
plot(data)


print(data.columns)

def save_to_google_sheet(data):
    gc = pygsheets.authorize(service_file='credentials.json')
    sh = gc.open("Reliance Trading Data")
    wks = sh[0]
    wks.clear()
    df = data.reset_index()
    wks.set_dataframe(df, (1, 1))
    
save_to_google_sheet(data)    
print("Data saved to Google Sheets successfully")