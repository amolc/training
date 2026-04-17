import pygsheets
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

# ── Config ──
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_NAME     = 'HA EMA 20 v2'

# ── SL / TP Config ──
SL_PCT = 0.005   # 0.5% stop loss
TP_PCT = 0.010   # 1.0% take profit

# ── Auth + Connect ──
gc = pygsheets.authorize(service_file=SERVICE_ACCOUNT_FILE)
sh = gc.open(SPREADSHEET_NAME)
print(f"✅ Connected to: {sh.title}")

# ── Fetch 5-min BTCUSD Data ──
tv   = TvDatafeed()
data = tv.get_hist(
    symbol='BTCUSD',
    exchange='BITSTAMP',
    interval=Interval.in_5_minute,
    n_bars=2000
)
data = data[['open', 'high', 'low', 'close', 'volume']].dropna()


# ──────────────────────────────────────────
# ── STRATEGY — Heikin Ashi + EMA 20 ──
# ──────────────────────────────────────────

ha = pd.DataFrame(index=data.index)
ha['ha_close'] = (data['open'] + data['high'] + data['low'] + data['close']) / 4

ha_open = [(data['open'].iloc[0] + data['close'].iloc[0]) / 2]
for i in range(1, len(ha)):
    ha_open.append((ha_open[i - 1] + ha['ha_close'].iloc[i - 1]) / 2)
ha['ha_open']  = ha_open
ha['ha_high']  = data[['high']].join(ha[['ha_open', 'ha_close']]).max(axis=1)
ha['ha_low']   = data[['low']].join(ha[['ha_open', 'ha_close']]).min(axis=1)

data['ha_open']  = ha['ha_open']
data['ha_high']  = ha['ha_high']
data['ha_low']   = ha['ha_low']
data['ha_close'] = ha['ha_close']

data['ema20']   = data['ha_close'].ewm(span=20, adjust=False).mean()
data['vol_sma'] = data['volume'].rolling(20).mean()

_delta      = data['close'].diff()
_gain       = _delta.clip(lower=0).ewm(com=13, adjust=False).mean()
_loss       = (-_delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
data['rsi'] = 100 - (100 / (1 + _gain / _loss))

data['ha_green'] = data['ha_close'] > data['ha_open']
data['ha_red']   = data['ha_close'] < data['ha_open']

data['prev_ha_close'] = data['ha_close'].shift(1)
data['prev_ema20']    = data['ema20'].shift(1)

ha_bull_cross = (data['ha_close'] > data['ema20']) & (data['prev_ha_close'] <= data['prev_ema20'])
ha_bear_cross = (data['ha_close'] < data['ema20']) & (data['prev_ha_close'] >= data['prev_ema20'])

data['buy_signal'] = (
    ha_bull_cross &
    data['ha_green'] &
    (data['volume'] >= data['vol_sma'] * 0.8)
)
data['sell_signal'] = (
    ha_bear_cross &
    data['ha_red'] &
    (data['volume'] >= data['vol_sma'] * 0.8)
)


# ──────────────────────────────────────────
# ── Trade Logic with SL / TP ──
# ──────────────────────────────────────────
trades   = []
position = None

for time, row in data.iterrows():

    # ── Entry ──
    if row['buy_signal'] and position is None:
        entry_price = row['close']
        position = {
            'entry_time':  time,
            'entry_price': entry_price,
            'sl':          round(entry_price * (1 - SL_PCT), 2),
            'tp':          round(entry_price * (1 + TP_PCT), 2),
        }

    # ── Exit Check (only when in position) ──
    elif position is not None:
        exit_price = None
        exit_reason = None

        # TP hit: HA high touched the target
        if row['ha_high'] >= position['tp']:
            exit_price  = position['tp']
            exit_reason = 'TP Hit'

        # SL hit: HA low touched the stop
        elif row['ha_low'] <= position['sl']:
            exit_price  = position['sl']
            exit_reason = 'SL Hit'

        # Signal-based exit (EMA crossover sell)
        elif row['sell_signal']:
            exit_price  = row['close']
            exit_reason = 'Signal Exit'

        if exit_price is not None:
            pnl = exit_price - position['entry_price']
            trades.append({
                'Entry Time':  position['entry_time'],
                'Exit Time':   time,
                'Entry Price': round(position['entry_price'], 2),
                'SL':          position['sl'],
                'TP':          position['tp'],
                'Exit Price':  round(exit_price, 2),
                'Exit Reason': exit_reason,
                'PnL':         round(pnl, 2),
                'Result':      'Win' if pnl > 0 else 'Loss'
            })
            position = None

trades_df = pd.DataFrame(trades)
print(f"\n✅ Total trades found: {len(trades_df)}")
print(trades_df)

# ── Win/Loss Summary ──
if len(trades_df) > 0:
    total_trades = len(trades_df)
    wins         = len(trades_df[trades_df['Result'] == 'Win'])
    losses       = len(trades_df[trades_df['Result'] == 'Loss'])
    tp_hits      = len(trades_df[trades_df['Exit Reason'] == 'TP Hit'])
    sl_hits      = len(trades_df[trades_df['Exit Reason'] == 'SL Hit'])
    sig_exits    = len(trades_df[trades_df['Exit Reason'] == 'Signal Exit'])
    win_rate     = round((wins / total_trades) * 100, 2)
    total_pnl    = round(trades_df['PnL'].sum(), 2)
    avg_win      = round(trades_df[trades_df['Result'] == 'Win']['PnL'].mean(), 2)  if wins   > 0 else 0
    avg_loss     = round(trades_df[trades_df['Result'] == 'Loss']['PnL'].mean(), 2) if losses > 0 else 0

    summary = pd.DataFrame([{
        'Total Trades':   total_trades,
        'Wins':           wins,
        'Losses':         losses,
        'Win Rate (%)':   win_rate,
        'Total PnL':      total_pnl,
        'Avg Win':        avg_win,
        'Avg Loss':       avg_loss,
        'TP Hits':        tp_hits,
        'SL Hits':        sl_hits,
        'Signal Exits':   sig_exits,
        'SL %':           f"{SL_PCT*100}%",
        'TP %':           f"{TP_PCT*100}%",
    }])
    print("\n── Summary ──")
    print(summary.T)


# ──────────────────────────────────────────
# ── Helper: write to sheet by title ──
# ──────────────────────────────────────────
def write_sheet_by_title(sh, df, sheet_title):
    try:
        wks = sh.worksheet_by_title(sheet_title)
    except pygsheets.WorksheetNotFound:
        wks = sh.add_worksheet(sheet_title)
    wks.clear('A1', None, '*')
    df_copy = df.copy()
    df_copy.columns = [str(c) for c in df_copy.columns]
    wks.set_dataframe(df_copy, (1, 1), copy_index=False, copy_head=True, fit=True)
    wks.frozen_rows = 1
    print(f"✅ Sheet '{wks.title}' written — {len(df_copy)} rows.")
    return wks

# ── Tab 1: Raw HA Data ──
export_df = data[['open','high','low','close','volume',
                  'ha_open','ha_high','ha_low','ha_close',
                  'ema20','rsi','buy_signal','sell_signal']].copy()
export_df.index   = export_df.index.astype(str)
export_df         = export_df.reset_index()
export_df.columns = [str(c) for c in export_df.columns]
write_sheet_by_title(sh, export_df, "HA_Data")

# ── Tab 2: Trade List ──
if len(trades_df) > 0:
    trades_export               = trades_df.copy()
    trades_export['Entry Time'] = trades_export['Entry Time'].astype(str)
    trades_export['Exit Time']  = trades_export['Exit Time'].astype(str)
    write_sheet_by_title(sh, trades_export, "Trades")

# ── Tab 3: Summary ──
if len(trades_df) > 0:
    write_sheet_by_title(sh, summary, "Summary")

print(f"\n🔗 Sheet URL: {sh.url}")


# ──────────────────────────────────────────
# ── Chart ──
# ──────────────────────────────────────────
import plotly.graph_objects as go
from plotly.subplots import make_subplots

fig = make_subplots(
    rows=3, cols=1, shared_xaxes=True,
    row_heights=[0.60, 0.20, 0.20],
    vertical_spacing=0.02,
    subplot_titles=('', 'RSI (14)', 'Volume')
)

fig.add_trace(go.Candlestick(
    x=data.index,
    open=data['ha_open'], high=data['ha_high'],
    low=data['ha_low'],   close=data['ha_close'],
    name='HA BTCUSD',
    increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
), row=1, col=1)

fig.add_trace(go.Scatter(x=data.index, y=data['ema20'], name='EMA 20',
    line=dict(color='#f7c948', width=1.8)), row=1, col=1)

buys  = data[data['buy_signal']]
sells = data[data['sell_signal']]
fig.add_trace(go.Scatter(x=buys.index,  y=buys['ha_low']  * 0.999,
    mode='markers', name='Buy',
    marker=dict(symbol='triangle-up',   color='#26a69a', size=12)), row=1, col=1)
fig.add_trace(go.Scatter(x=sells.index, y=sells['ha_high'] * 1.001,
    mode='markers', name='Sell',
    marker=dict(symbol='triangle-down', color='#ef5350', size=12)), row=1, col=1)

# ── SL / TP lines per trade ──
for _, t in trades_df.iterrows():
    fig.add_trace(go.Scatter(
        x=[t['Entry Time'], t['Exit Time']],
        y=[t['SL'], t['SL']],
        mode='lines', name='SL',
        line=dict(color='#ef5350', width=1, dash='dot'),
        showlegend=False
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=[t['Entry Time'], t['Exit Time']],
        y=[t['TP'], t['TP']],
        mode='lines', name='TP',
        line=dict(color='#26a69a', width=1, dash='dot'),
        showlegend=False
    ), row=1, col=1)

fig.add_trace(go.Scatter(x=data.index, y=data['rsi'], name='RSI',
    line=dict(color='#f7c948', width=1.2)), row=2, col=1)
fig.add_hline(y=70, line_dash='dot', line_color='#ef5350', row=2, col=1)
fig.add_hline(y=30, line_dash='dot', line_color='#26a69a', row=2, col=1)

fig.add_trace(go.Bar(x=data.index, y=data['volume'], name='Volume',
    marker_color='#888888'), row=3, col=1)

fig.update_layout(
    title='BTCUSD 5-Min | Heikin Ashi + EMA 20 | SL/TP Strategy',
    template='plotly_dark',
    height=800,
    xaxis_rangeslider_visible=False,
    hovermode='x unified',
    xaxis=dict(type='category', nticks=10, tickangle=-45)
)
fig.update_yaxes(title_text='Price',  row=1, col=1)
fig.update_yaxes(title_text='RSI',    row=2, col=1, range=[0, 100])
fig.update_yaxes(title_text='Volume', row=3, col=1)

fig.show()