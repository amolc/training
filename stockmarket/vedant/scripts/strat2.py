import pygsheets
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Config ──────────────────────────────────────────
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_NAME     = 'HA EMA20'

# ── Auth + Connect ───────────────────────────────────
gc = pygsheets.authorize(service_file=SERVICE_ACCOUNT_FILE)
sh = gc.open(SPREADSHEET_NAME)
print(f"✅ Connected to: {sh.title}")


# ── Fetch 5-min BTCUSD Data ─────────────────────────
tv = TvDatafeed()
data = tv.get_hist(
    symbol='BTCUSD',
    exchange='BITSTAMP',        # change to BINANCE (BTCUSDT) if preferred
    interval=Interval.in_5_minute,
    n_bars=500
)
data = data[['open', 'high', 'low', 'close', 'volume']].dropna()


# ────────────────────────────────────────────────────
# ── Heikin-Ashi Calculation ──────────────────────────
# ────────────────────────────────────────────────────
ha_close = (data['open'] + data['high'] + data['low'] + data['close']) / 4
ha_open  = ha_close.copy()
ha_open.iloc[0] = (data['open'].iloc[0] + data['close'].iloc[0]) / 2

for i in range(1, len(ha_open)):
    ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2

ha_high = pd.concat([data['high'], ha_open, ha_close], axis=1).max(axis=1)
ha_low  = pd.concat([data['low'],  ha_open, ha_close], axis=1).min(axis=1)

data['ha_open']  = ha_open
data['ha_high']  = ha_high
data['ha_low']   = ha_low
data['ha_close'] = ha_close


# ── EMA 20 Channel (on HA High & Low) ───────────────
data['ema20_high'] = data['ha_high'].ewm(span=20, adjust=False).mean()
data['ema20_low']  = data['ha_low'].ewm(span=20, adjust=False).mean()


# ── Candle Color ─────────────────────────────────────
data['ha_green'] = data['ha_close'] >= data['ha_open']   # bullish
data['ha_red']   = data['ha_close'] <  data['ha_open']   # bearish


# ────────────────────────────────────────────────────
# ── Strategy Signals ─────────────────────────────────
#
#  LONG  → Green HA candle closes ABOVE EMA20 HIGH (breakout above upper channel)
#  EXIT LONG  → HA candle closes BELOW EMA20 HIGH
#
#  SHORT → Red HA candle closes BELOW EMA20 LOW (breakdown below lower channel)
#  EXIT SHORT → HA candle closes ABOVE EMA20 LOW
# ────────────────────────────────────────────────────
data['long_entry']  = data['ha_green'] & (data['ha_close'] > data['ema20_high'])
data['short_entry'] = data['ha_red']   & (data['ha_close'] < data['ema20_low'])

data['long_exit']   = data['ha_close'] < data['ema20_high']
data['short_exit']  = data['ha_close'] > data['ema20_low']


# ────────────────────────────────────────────────────
# ── Trade Logic ──────────────────────────────────────
# ────────────────────────────────────────────────────
trades   = []
position = None       # 'long' | 'short'
entry    = {}

for time, row in data.iterrows():

    # ── No open position → look for entry ──
    if position is None:
        if row['long_entry']:
            position = 'long'
            entry = {'time': time, 'price': row['ha_close']}

        elif row['short_entry']:
            position = 'short'
            entry = {'time': time, 'price': row['ha_close']}

    # ── In a LONG → watch for exit ──
    elif position == 'long':
        if row['long_exit']:
            exit_price = row['ha_close']
            pnl        = exit_price - entry['price']
            trades.append({
                'Type':         'Long',
                'Entry Time':   entry['time'],
                'Exit Time':    time,
                'Entry Price':  round(entry['price'], 2),
                'Exit Price':   round(exit_price, 2),
                'PnL':          round(pnl, 2),
                'Result':       'Win' if pnl > 0 else 'Loss'
            })
            position = None
            entry    = {}

    # ── In a SHORT → watch for exit ──
    elif position == 'short':
        if row['short_exit']:
            exit_price = row['ha_close']
            pnl        = entry['price'] - exit_price    # short profit = entry - exit
            trades.append({
                'Type':         'Short',
                'Entry Time':   entry['time'],
                'Exit Time':    time,
                'Entry Price':  round(entry['price'], 2),
                'Exit Price':   round(exit_price, 2),
                'PnL':          round(pnl, 2),
                'Result':       'Win' if pnl > 0 else 'Loss'
            })
            position = None
            entry    = {}


trades_df = pd.DataFrame(trades)
print(f"\n✅ Total trades: {len(trades_df)}")
print(trades_df)


# ────────────────────────────────────────────────────
# ── Win / Loss Summary ───────────────────────────────
# ────────────────────────────────────────────────────
if len(trades_df) > 0:
    total   = len(trades_df)
    wins    = len(trades_df[trades_df['Result'] == 'Win'])
    losses  = len(trades_df[trades_df['Result'] == 'Loss'])
    longs   = len(trades_df[trades_df['Type']   == 'Long'])
    shorts  = len(trades_df[trades_df['Type']   == 'Short'])

    summary = pd.DataFrame([{
        'Total Trades': total,
        'Longs':        longs,
        'Shorts':       shorts,
        'Wins':         wins,
        'Losses':       losses,
        'Win Rate (%)': round(wins / total * 100, 2),
        'Total PnL':    round(trades_df['PnL'].sum(), 2),
        'Avg Win':      round(trades_df[trades_df['Result'] == 'Win']['PnL'].mean(), 2) if wins > 0 else 0,
        'Avg Loss':     round(trades_df[trades_df['Result'] == 'Loss']['PnL'].mean(), 2) if losses > 0 else 0,
    }])

    print("\n── Summary ──")
    print(summary.T)


# ────────────────────────────────────────────────────
# ── Helper: write tab to Google Sheet ────────────────
# ────────────────────────────────────────────────────
def write_tab(sh, tab_name, df):
    try:
        wks = sh.worksheet_by_title(tab_name)
    except pygsheets.WorksheetNotFound:
        wks = sh.add_worksheet(tab_name)
    wks.clear('A1', None, '*')
    df_copy         = df.copy()
    df_copy.columns = [str(c) for c in df_copy.columns]
    wks.set_dataframe(df_copy, (1, 1), copy_index=False, copy_head=True, fit=True)
    wks.frozen_rows = 1
    print(f"✅ '{tab_name}' written — {len(df_copy)} rows.")


# ── Tab 1: Raw HA + EMA Channel Data ────────────────
export_cols = [
    'open', 'high', 'low', 'close', 'volume',
    'ha_open', 'ha_high', 'ha_low', 'ha_close',
    'ema20_high', 'ema20_low',
    'long_entry', 'short_entry', 'long_exit', 'short_exit'
]
export_df       = data[export_cols].copy()
export_df.index = export_df.index.astype(str)
export_df       = export_df.reset_index()
export_df.columns = [str(c) for c in export_df.columns]
write_tab(sh, 'HA_EMA_Data', export_df)

# ── Tab 2: Trade List ────────────────────────────────
if len(trades_df) > 0:
    trades_export               = trades_df.copy()
    trades_export['Entry Time'] = trades_export['Entry Time'].astype(str)
    trades_export['Exit Time']  = trades_export['Exit Time'].astype(str)
    write_tab(sh, 'Trades', trades_export)

# ── Tab 3: Summary ───────────────────────────────────
if len(trades_df) > 0:
    write_tab(sh, 'Summary', summary)

print(f"\n🔗 Sheet URL: {sh.url}")


# ────────────────────────────────────────────────────
# ── Plotly Chart ─────────────────────────────────────
# ────────────────────────────────────────────────────
fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.75, 0.25],
    vertical_spacing=0.03
)

# ── Heikin-Ashi Candlestick ──────────────────────────
fig.add_trace(go.Candlestick(
    x=data.index,
    open=data['ha_open'],  high=data['ha_high'],
    low=data['ha_low'],    close=data['ha_close'],
    name='BTC/USD (HA)',
    increasing_line_color='#26a69a',
    decreasing_line_color='#ef5350'
), row=1, col=1)

# ── EMA 20 HIGH — upper channel ──────────────────────
fig.add_trace(go.Scatter(
    x=data.index, y=data['ema20_high'],
    name='EMA 20 High',
    line=dict(color='#4f9cf0', width=1.5, dash='dot')
), row=1, col=1)

# ── EMA 20 LOW — lower channel ───────────────────────
fig.add_trace(go.Scatter(
    x=data.index, y=data['ema20_low'],
    name='EMA 20 Low',
    line=dict(color='#f7c948', width=1.5, dash='dot'),
    fill='tonexty',                      # fills the channel between the two EMAs
    fillcolor='rgba(100, 100, 255, 0.07)'
), row=1, col=1)

# ── Long Entry Markers ────────────────────────────────
long_entries = data[data['long_entry']]
fig.add_trace(go.Scatter(
    x=long_entries.index,
    y=long_entries['ha_low'] * 0.999,
    mode='markers', name='Long Entry',
    marker=dict(symbol='triangle-up', color='#26a69a', size=12)
), row=1, col=1)

# ── Short Entry Markers ───────────────────────────────
short_entries = data[data['short_entry']]
fig.add_trace(go.Scatter(
    x=short_entries.index,
    y=short_entries['ha_high'] * 1.001,
    mode='markers', name='Short Entry',
    marker=dict(symbol='triangle-down', color='#ef5350', size=12)
), row=1, col=1)

# ── Volume ────────────────────────────────────────────
fig.add_trace(go.Bar(
    x=data.index, y=data['volume'],
    name='Volume',
    marker_color='#888888'
), row=2, col=1)

# ── Layout ────────────────────────────────────────────
fig.update_layout(
    title='BTC/USD 5-Min | Heikin-Ashi + EMA 20 High/Low Channel Strategy',
    template='plotly_dark',
    height=750,
    xaxis_rangeslider_visible=False,
    hovermode='x unified',
    xaxis=dict(type='category', nticks=10, tickangle=-45),
    legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='left', x=0)
)
fig.update_yaxes(title_text='Price (USD)',  row=1, col=1)
fig.update_yaxes(title_text='Volume',       row=2, col=1)

fig.show()