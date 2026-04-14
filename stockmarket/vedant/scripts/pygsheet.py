import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tvDatafeed import TvDatafeed, Interval
import pygsheets  # <-- added
# ── Authorize Google Sheets (use your existing credentials path) ──
gc = pygsheets.authorize(service_file='credentials.json')

# ── Fetch AAPL 1-minute data via tvDatafeed ──
tv = TvDatafeed()  # optional: TvDatafeed(username='your_email', password='your_pass')
data = tv.get_hist(
    symbol='AAPL',
    exchange='NASDAQ',
    interval=Interval.in_1_minute,
    n_bars=500          # increase as needed
)
data = data[['open', 'high', 'low', 'close', 'volume']].dropna()

# ── EMA 3, 9, 21 ──
data['ema3']  = data['close'].ewm(span=3,  adjust=False).mean()
data['ema9']  = data['close'].ewm(span=9,  adjust=False).mean()
data['ema21'] = data['close'].ewm(span=21, adjust=False).mean()

# ── ATR (14-period) ──
prev_close = data['close'].shift(1)
tr = pd.concat([
    data['high'] - data['low'],
    (data['high'] - prev_close).abs(),
    (data['low']  - prev_close).abs()
], axis=1).max(axis=1)
data['atr14'] = tr.rolling(14).mean()

# ── Crossover Detection ──
def detect_crossovers(fast, slow, pair_name):
    above   = fast > slow
    bullish = above & ~above.shift(1).fillna(False)
    bearish = ~above & above.shift(1).fillna(True)
    result  = pd.Series('', index=fast.index)
    result[bullish] = f'{pair_name} Bullish'
    result[bearish] = f'{pair_name} Bearish'
    return result

data['co_ema3_ema9']  = detect_crossovers(data['ema3'], data['ema9'],  'EMA3xEMA9')
data['co_ema3_ema21'] = detect_crossovers(data['ema3'], data['ema21'], 'EMA3xEMA21')
data['co_ema9_ema21'] = detect_crossovers(data['ema9'], data['ema21'], 'EMA9xEMA21')

# ── Running Cumulative Crossover Counts ──
data['count_co_ema3_ema9']  = (data['co_ema3_ema9']  != '').cumsum()
data['count_co_ema3_ema21'] = (data['co_ema3_ema21'] != '').cumsum()
data['count_co_ema9_ema21'] = (data['co_ema9_ema21'] != '').cumsum()

# ── Print Summary ──
print(f"Total bars        : {len(data)}")
print(f"EMA3×EMA9  crosses: {(data['co_ema3_ema9']  != '').sum()}")
print(f"EMA3×EMA21 crosses: {(data['co_ema3_ema21'] != '').sum()}")
print(f"EMA9×EMA21 crosses: {(data['co_ema9_ema21'] != '').sum()}")
print("\nLast 5 rows preview:")
print(data[['close','ema3','ema9','ema21','co_ema3_ema9','co_ema3_ema21','co_ema9_ema21']].tail())

# ── Save to CSV (optional) ──
data.to_csv('ema_crossovers.csv')
print("\nSaved → ema_crossovers.csv")

# ========== NEW: UPLOAD TO GOOGLE SHEETS ==========
# Create or open a spreadsheet
try:
    sh = gc.open('EMA')
    print("Opened existing spreadsheet: EMA")
except pygsheets.SpreadsheetNotFound:
    sh = gc.create('EMA')
    print("Created new spreadsheet: EMA")

# Select the first worksheet (or create one)
try:
    wks_data = sh.worksheet_by_title("Full Data")
except pygsheets.WorksheetNotFound:
    wks_data = sh.add_worksheet("Full Data", rows=len(data)+1, cols=len(data.columns)+5)

# Reset index to a column (datetime index -> string)
df_to_upload = data.reset_index().copy()
df_to_upload.columns = [str(col) for col in df_to_upload.columns]  # ensure column names are strings

# Upload the entire DataFrame (including index as a column)
wks_data.set_dataframe(df_to_upload, start='A1')

print(f"Uploaded {len(df_to_upload)} rows to Google Sheet 'Full Data'")

# Optional: Create a second sheet with summary statistics
try:
    wks_summary = sh.worksheet_by_title("Summary")
except pygsheets.WorksheetNotFound:
    wks_summary = sh.add_worksheet("Summary", rows=10, cols=2)

summary_data = {
    "Metric": ["Total bars", "EMA3×EMA9 crosses", "EMA3×EMA21 crosses", "EMA9×EMA21 crosses", "Last update"],
    "Value": [len(data), (data['co_ema3_ema9'] != '').sum(), (data['co_ema3_ema21'] != '').sum(), (data['co_ema9_ema21'] != '').sum(), pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")]
}
df_summary = pd.DataFrame(summary_data)
wks_summary.set_dataframe(df_summary, start='A1')

print("Uploaded summary to sheet 'Summary'")

# ── Plotly Chart (unchanged) ──
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.75, 0.25],
                    vertical_spacing=0.03)

# Candlestick
fig.add_trace(go.Candlestick(
    x=data.index, open=data['open'], high=data['high'],
    low=data['low'], close=data['close'], name='AAPL',
    increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
), row=1, col=1)

# EMA lines
fig.add_trace(go.Scatter(x=data.index, y=data['ema3'],  name='EMA 3',
    line=dict(color='#f7c948', width=1.2)), row=1, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data['ema9'],  name='EMA 9',
    line=dict(color='#4f9cf0', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data['ema21'], name='EMA 21',
    line=dict(color='#b06ef7', width=2.0)), row=1, col=1)

def add_markers(fig, data, col, bull_symbol, bear_symbol, bull_color, bear_color, name_prefix):
    bull_mask = data[col].str.contains('Bullish', na=False)
    bear_mask = data[col].str.contains('Bearish', na=False)

    fig.add_trace(go.Scatter(
        x=data[bull_mask].index,
        y=data[bull_mask]['low'] * 0.9995,
        mode='markers', name=f'{name_prefix} ▲',
        marker=dict(symbol=bull_symbol, color=bull_color, size=10,
                    line=dict(color='white', width=0.5))
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=data[bear_mask].index,
        y=data[bear_mask]['high'] * 1.0005,
        mode='markers', name=f'{name_prefix} ▼',
        marker=dict(symbol=bear_symbol, color=bear_color, size=10,
                    line=dict(color='white', width=0.5))
    ), row=1, col=1)

add_markers(fig, data, 'co_ema3_ema9',  'triangle-up', 'triangle-down',
            '#26a69a', '#ef5350', 'EMA3×9')
add_markers(fig, data, 'co_ema3_ema21', 'star',        'x',
            '#a5d6a7', '#ef9a9a', 'EMA3×21')
add_markers(fig, data, 'co_ema9_ema21', 'diamond',     'cross',
            '#b06ef7', '#f76e6e', 'EMA9×21')

# ATR subplot
fig.add_trace(go.Scatter(
    x=data.index, y=data['atr14'], name='ATR 14',
    line=dict(color='#ffb74d', width=1.2),
    fill='tozeroy', fillcolor='rgba(255,183,77,0.1)'
), row=2, col=1)

fig.update_layout(
    title='AAPL 1-Min | EMA 3/9/21 Crossover Strategy',
    xaxis_rangeslider_visible=False,
    template='plotly_dark',
    height=700,
    hovermode='x unified',
    legend=dict(orientation='h', yanchor='bottom', y=1.01)
)
fig.update_yaxes(title_text='Price', row=1, col=1)
fig.update_yaxes(title_text='ATR',   row=2, col=1)

fig.show()