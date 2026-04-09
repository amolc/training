import yfinance as yf
import pandas as pd
from pathlib import Path

# Define ticker (example: Reliance)


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


def createchart(df):
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
        from plotly.subplots import make_subplots
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "plotly is required for createchart(). "
            "Install it with pip install plotly."
        ) from exc

    if df.empty:
        raise ValueError("Cannot create chart from an empty dataframe.")

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
    )

    has_ohlc = all(
        col in df.columns for col in ["Open", "High", "Low", "Close"]
    )
    if has_ohlc:
        figure.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="Price",
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
    createchart(df)
