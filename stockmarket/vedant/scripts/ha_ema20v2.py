import pygsheets
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tvDatafeed import TvDatafeed, Interval

# ══════════════════════════════════════════
# ── CONFIG  (edit here only) ──
# ══════════════════════════════════════════
CONFIG = {
    'service_account': 'credentials.json',
    'spreadsheet':     'HA EMA 20 v2',
    'symbol':          'BTCUSD',
    'exchange':        'BITSTAMP',
    'interval':        Interval.in_5_minute,
    'n_bars':          2000,
    'ema_span':        20,
    'vol_sma_period':  20,
    'sl_pct':          0.005,   # 0.5% stop loss
    'tp_pct':          0.010,   # 1.0% take profit
}


# ══════════════════════════════════════════
# ── AUTH + DATA ──
# ══════════════════════════════════════════
gc = pygsheets.authorize(service_file=CONFIG['service_account'])
sh = gc.open(CONFIG['spreadsheet'])
print(f"✅ Connected: {sh.title}")

tv   = TvDatafeed()
data = tv.get_hist(
    symbol=CONFIG['symbol'],
    exchange=CONFIG['exchange'],
    interval=CONFIG['interval'],
    n_bars=CONFIG['n_bars']
)
data = data[['open', 'high', 'low', 'close', 'volume']].dropna().copy()


# ══════════════════════════════════════════
# ── HEIKIN ASHI (fully vectorized) ──
# ══════════════════════════════════════════
data['ha_close'] = (data['open'] + data['high'] + data['low'] + data['close']) / 4

# Vectorized HA Open using EWM (span=2, adjust=False ≈ iterative midpoint formula)
ha_open_seed = (data['open'].iloc[0] + data['close'].iloc[0]) / 2
data['ha_open'] = (
    data['ha_close']
    .shift(1)
    .fillna(ha_open_seed)
    .ewm(span=2, adjust=False, min_periods=1)
    .mean()
)
data['ha_high'] = data[['high', 'ha_open', 'ha_close']].max(axis=1)
data['ha_low']  = data[['low',  'ha_open', 'ha_close']].min(axis=1)


# ══════════════════════════════════════════
# ── INDICATORS ──
# ══════════════════════════════════════════
span = CONFIG['ema_span']
data['ema20']   = data['ha_close'].ewm(span=span, adjust=False).mean()
data['vol_sma'] = data['volume'].rolling(CONFIG['vol_sma_period']).mean()

# RSI (14) — vectorized
delta         = data['close'].diff()
gain          = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
loss          = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
data['rsi']   = 100 - (100 / (1 + gain / loss))


# ══════════════════════════════════════════
# ── SIGNALS (vectorized) ──
# ══════════════════════════════════════════
prev_ha  = data['ha_close'].shift(1)
prev_ema = data['ema20'].shift(1)

bull_cross = (data['ha_close'] > data['ema20']) & (prev_ha <= prev_ema)
bear_cross = (data['ha_close'] < data['ema20']) & (prev_ha >= prev_ema)

vol_ok = data['volume'] >= data['vol_sma'] * 0.8

data['buy_signal']  = bull_cross & (data['ha_close'] > data['ha_open']) & vol_ok
data['sell_signal'] = bear_cross & (data['ha_close'] < data['ha_open']) & vol_ok


# ══════════════════════════════════════════
# ── TRADE LOOP WITH SL / TP ──
# ══════════════════════════════════════════
SL_PCT = CONFIG['sl_pct']
TP_PCT = CONFIG['tp_pct']

trades   = []
position = None

for time, row in data.iterrows():

    if row['buy_signal'] and position is None:
        ep = row['close']
        position = {
            'entry_time':  time,
            'entry_price': ep,
            'sl':          round(ep * (1 - SL_PCT), 2),
            'tp':          round(ep * (1 + TP_PCT), 2),
        }

    elif position is not None:
        exit_price = exit_reason = None

        if   row['ha_high'] >= position['tp']:   exit_price, exit_reason = position['tp'],    'TP Hit'
        elif row['ha_low']  <= position['sl']:   exit_price, exit_reason = position['sl'],    'SL Hit'
        elif row['sell_signal']:                 exit_price, exit_reason = row['close'],      'Signal Exit'

        if exit_price is not None:
            pnl = round(exit_price - position['entry_price'], 2)
            trades.append({
                'Entry Time':  position['entry_time'],
                'Exit Time':   time,
                'Entry Price': round(position['entry_price'], 2),
                'SL':          position['sl'],
                'TP':          position['tp'],
                'Exit Price':  round(exit_price, 2),
                'Exit Reason': exit_reason,
                'PnL':         pnl,
                'Result':      'Win' if pnl > 0 else 'Loss',
            })
            position = None

trades_df = pd.DataFrame(trades)
print(f"\n✅ Trades: {len(trades_df)}")
print(trades_df.to_string())


# ══════════════════════════════════════════
# ── SUMMARY ──
# ══════════════════════════════════════════
summary = pd.DataFrame()
if len(trades_df) > 0:
    wins    = trades_df['Result'].eq('Win')
    losses  = trades_df['Result'].eq('Loss')
    summary = pd.DataFrame([{
        'Total Trades':  len(trades_df),
        'Wins':          wins.sum(),
        'Losses':        losses.sum(),
        'Win Rate (%)':  round(wins.mean() * 100, 2),
        'Total PnL':     round(trades_df['PnL'].sum(), 2),
        'Avg Win':       round(trades_df.loc[wins,   'PnL'].mean(), 2),
        'Avg Loss':      round(trades_df.loc[losses, 'PnL'].mean(), 2),
        'Best Trade':    trades_df['PnL'].max(),
        'Worst Trade':   trades_df['PnL'].min(),
        'TP Hits':       trades_df['Exit Reason'].eq('TP Hit').sum(),
        'SL Hits':       trades_df['Exit Reason'].eq('SL Hit').sum(),
        'Signal Exits':  trades_df['Exit Reason'].eq('Signal Exit').sum(),
        'SL %':          f"{SL_PCT*100}%",
        'TP %':          f"{TP_PCT*100}%",
    }])
    print("\n── Summary ──")
    print(summary.T.to_string())


# ══════════════════════════════════════════
# ── GOOGLE SHEETS EXPORT ──
# ══════════════════════════════════════════
def write_sheet(sh, df, title):
    """Write DataFrame to a named sheet tab (create if missing)."""
    try:
        wks = sh.worksheet_by_title(title)
    except pygsheets.WorksheetNotFound:
        wks = sh.add_worksheet(title)
    wks.clear('A1', None, '*')
    df_out          = df.copy().reset_index(drop=True)
    df_out.columns  = df_out.columns.astype(str)
    wks.set_dataframe(df_out, (1, 1), copy_index=False, copy_head=True, fit=True)
    wks.frozen_rows = 1
    print(f"✅ '{title}' → {len(df_out)} rows")
    return wks

# ── Prepare export_df ──
export_df       = data[['open','high','low','close','volume',
                         'ha_open','ha_high','ha_low','ha_close',
                         'ema20','rsi','buy_signal','sell_signal']].copy()
export_df.index = export_df.index.astype(str)
export_df       = export_df.reset_index()

write_sheet(sh, export_df, "HA_Data")

if len(trades_df) > 0:
    t_export                = trades_df.copy()
    t_export['Entry Time']  = t_export['Entry Time'].astype(str)
    t_export['Exit Time']   = t_export['Exit Time'].astype(str)
    write_sheet(sh, t_export, "Trades")
    write_sheet(sh, summary,  "Summary")

print(f"\n🔗 {sh.url}")


# ══════════════════════════════════════════
# ── CHART ──
# ══════════════════════════════════════════
fig = make_subplots(
    rows=3, cols=1, shared_xaxes=True,
    row_heights=[0.60, 0.20, 0.20],
    vertical_spacing=0.02,
    subplot_titles=('', 'RSI (14)', 'Volume')
)

# ── Heikin Ashi candles ──
fig.add_trace(go.Candlestick(
    x=data.index, open=data['ha_open'], high=data['ha_high'],
    low=data['ha_low'], close=data['ha_close'], name='HA BTCUSD',
    increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
), row=1, col=1)

# ── EMA 20 ──
fig.add_trace(go.Scatter(x=data.index, y=data['ema20'], name='EMA 20',
    line=dict(color='#f7c948', width=1.8)), row=1, col=1)

# ── Buy / Sell markers ──
buys  = data[data['buy_signal']]
sells = data[data['sell_signal']]
fig.add_trace(go.Scatter(x=buys.index,  y=buys['ha_low']   * 0.999, mode='markers',
    name='Buy',  marker=dict(symbol='triangle-up',   color='#26a69a', size=12)), row=1, col=1)
fig.add_trace(go.Scatter(x=sells.index, y=sells['ha_high'] * 1.001, mode='markers',
    name='Sell', marker=dict(symbol='triangle-down', color='#ef5350', size=12)), row=1, col=1)

# ── SL / TP bands (single trace each — much faster than per-trade traces) ──
if len(trades_df) > 0:
    sl_x, sl_y, tp_x, tp_y = [], [], [], []
    for _, t in trades_df.iterrows():
        sl_x += [t['Entry Time'], t['Exit Time'], None]
        sl_y += [t['SL'],         t['SL'],         None]
        tp_x += [t['Entry Time'], t['Exit Time'], None]
        tp_y += [t['TP'],         t['TP'],         None]

    fig.add_trace(go.Scatter(x=sl_x, y=sl_y, mode='lines', name='Stop Loss',
        line=dict(color='#ef5350', width=1, dash='dot')), row=1, col=1)
    fig.add_trace(go.Scatter(x=tp_x, y=tp_y, mode='lines', name='Take Profit',
        line=dict(color='#26a69a', width=1, dash='dot')), row=1, col=1)

# ── RSI ──
fig.add_trace(go.Scatter(x=data.index, y=data['rsi'], name='RSI',
    line=dict(color='#f7c948', width=1.2)), row=2, col=1)
fig.add_hline(y=70, line_dash='dot', line_color='#ef5350', row=2, col=1)
fig.add_hline(y=30, line_dash='dot', line_color='#26a69a', row=2, col=1)

# ── Volume ──
fig.add_trace(go.Bar(x=data.index, y=data['volume'], name='Volume',
    marker_color='#888888'), row=3, col=1)

fig.update_layout(
    title='BTCUSD 5-Min | Heikin Ashi + EMA 20 | Optimized',
    template='plotly_dark', height=800,
    xaxis_rangeslider_visible=False,
    hovermode='x unified',
    xaxis=dict(type='category', nticks=10, tickangle=-45)
)
fig.update_yaxes(title_text='Price',  row=1, col=1)
fig.update_yaxes(title_text='RSI',    row=2, col=1, range=[0, 100])
fig.update_yaxes(title_text='Volume', row=3, col=1)

fig.show()