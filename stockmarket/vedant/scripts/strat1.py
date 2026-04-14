import pygsheets
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

# ── Config ──
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_NAME     = 'EMA 3/9'

# ── Auth + Connect ──
gc = pygsheets.authorize(service_file=SERVICE_ACCOUNT_FILE)
sh = gc.open(SPREADSHEET_NAME)
print(f"✅ Connected to: {sh.title}")

# ── Fetch 5-min AAPL Data ──
tv = TvDatafeed()
data = tv.get_hist(
    symbol='AAPL',
    exchange='NASDAQ',
    interval=Interval.in_5_minute,
    n_bars=500
)
data = data[['open', 'high', 'low', 'close', 'volume']].dropna()

# ── EMA 3 and EMA 9 only ──
data['ema3'] = data['close'].ewm(span=3, adjust=False).mean()
data['ema9'] = data['close'].ewm(span=9, adjust=False).mean()

# ── Crossover Signals ──
data['prev_ema3'] = data['ema3'].shift(1)
data['prev_ema9'] = data['ema9'].shift(1)

data['buy_signal']  = (data['ema3'] > data['ema9']) & (data['prev_ema3'] <= data['prev_ema9'])
data['sell_signal'] = (data['ema3'] < data['ema9']) & (data['prev_ema3'] >= data['prev_ema9'])

# ──────────────────────────────────────────
# ── Trade Logic ──
# Buy on bullish crossover, sell on bearish crossover
# ──────────────────────────────────────────
trades = []
position = None   # holds {'entry_time', 'entry_price'}

for time, row in data.iterrows():
    if row['buy_signal'] and position is None:
        # Enter trade
        position = {
            'entry_time':  time,
            'entry_price': row['close']
        }

    elif row['sell_signal'] and position is not None:
        # Exit trade
        exit_price = row['close']
        pnl        = exit_price - position['entry_price']
        trades.append({
            'Entry Time':   position['entry_time'],
            'Exit Time':    time,
            'Entry Price':  round(position['entry_price'], 2),
            'Exit Price':   round(exit_price, 2),
            'PnL':          round(pnl, 2),
            'Result':       'Win' if pnl > 0 else 'Loss'
        })
        position = None   # reset

trades_df = pd.DataFrame(trades)
print(f"\n✅ Total trades found: {len(trades_df)}")
print(trades_df)

# ──────────────────────────────────────────
# ── Win/Loss Summary ──
# ──────────────────────────────────────────
if len(trades_df) > 0:
    total_trades = len(trades_df)
    wins         = len(trades_df[trades_df['Result'] == 'Win'])
    losses       = len(trades_df[trades_df['Result'] == 'Loss'])
    win_rate     = round((wins / total_trades) * 100, 2)
    total_pnl    = round(trades_df['PnL'].sum(), 2)
    avg_win      = round(trades_df[trades_df['Result'] == 'Win']['PnL'].mean(), 2) if wins > 0 else 0
    avg_loss     = round(trades_df[trades_df['Result'] == 'Loss']['PnL'].mean(), 2) if losses > 0 else 0

    summary = pd.DataFrame([{
        'Total Trades': total_trades,
        'Wins':         wins,
        'Losses':       losses,
        'Win Rate (%)': win_rate,
        'Total PnL':    total_pnl,
        'Avg Win':      avg_win,
        'Avg Loss':     avg_loss
    }])

    print("\n── Summary ──")
    print(summary.T)   # print vertically for readability

# ──────────────────────────────────────────
# ── Helper: write tab to Google Sheet ──
# ──────────────────────────────────────────
def write_tab(sh, tab_name, df):
    try:
        wks = sh.worksheet_by_title(tab_name)
    except pygsheets.WorksheetNotFound:
        wks = sh.add_worksheet(tab_name)
    wks.clear('A1', None, '*')
    df_copy = df.copy()
    df_copy.columns = [str(c) for c in df_copy.columns]
    wks.set_dataframe(df_copy, (1, 1), copy_index=False, copy_head=True, fit=True)
    wks.frozen_rows = 1
    print(f"✅ '{tab_name}' tab written — {len(df_copy)} rows.")

# ── Tab 1: Raw EMA Data ──
export_df = data[['open', 'high', 'low', 'close', 'volume', 'ema3', 'ema9', 'buy_signal', 'sell_signal']].copy()
export_df.index = export_df.index.astype(str)
export_df = export_df.reset_index()
export_df.columns = [str(c) for c in export_df.columns]
write_tab(sh, 'EMA_Data', export_df)

# ── Tab 2: Trade List ──
if len(trades_df) > 0:
    trades_export = trades_df.copy()
    trades_export['Entry Time'] = trades_export['Entry Time'].astype(str)
    trades_export['Exit Time']  = trades_export['Exit Time'].astype(str)
    write_tab(sh, 'Trades', trades_export)

# ── Tab 3: Win/Loss Summary ──
if len(trades_df) > 0:
    write_tab(sh, 'Summary', summary)

print(f"\n🔗 Sheet URL: {sh.url}")

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Plot ──
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.75, 0.25], vertical_spacing=0.03)

# Candlestick
fig.add_trace(go.Candlestick(
    x=data.index, open=data['open'], high=data['high'],
    low=data['low'], close=data['close'], name='AAPL',
    increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
), row=1, col=1)

# EMA Lines
fig.add_trace(go.Scatter(x=data.index, y=data['ema3'], name='EMA 3',
    line=dict(color='#f7c948', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data['ema9'], name='EMA 9',
    line=dict(color='#4f9cf0', width=1.5)), row=1, col=1)

# Buy Markers
buys = data[data['buy_signal']]
fig.add_trace(go.Scatter(x=buys.index, y=buys['low'] * 0.999,
    mode='markers', name='Buy',
    marker=dict(symbol='triangle-up', color='#26a69a', size=12)), row=1, col=1)

# Sell Markers
sells = data[data['sell_signal']]
fig.add_trace(go.Scatter(x=sells.index, y=sells['high'] * 1.001,
    mode='markers', name='Sell',
    marker=dict(symbol='triangle-down', color='#ef5350', size=12)), row=1, col=1)

# Volume
fig.add_trace(go.Bar(x=data.index, y=data['volume'], name='Volume',
    marker_color='#888888'), row=2, col=1)

fig.update_layout(
    title='AAPL 5-Min | EMA 3 & 9 Crossover',
    template='plotly_dark',
    height=700,
    xaxis_rangeslider_visible=False,
    hovermode='x unified',
    xaxis=dict(
        type='category',
        nticks=10,
        tickangle=-45
    )
)
fig.update_yaxes(title_text='Price',  row=1, col=1)
fig.update_yaxes(title_text='Volume', row=2, col=1)

fig.show()