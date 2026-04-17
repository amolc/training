import pygsheets
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tvDatafeed import TvDatafeed, Interval

# ══════════════════════════════════════════
# ── CONFIG
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
    'sl_pct':          0.005,
    'tp_pct':          0.010,
}


# ══════════════════════════════════════════
# ── 1. DATA FETCH
# ══════════════════════════════════════════
def fetch_data(cfg: dict) -> pd.DataFrame:
    """Fetch OHLCV data from TradingView."""
    tv   = TvDatafeed()
    data = tv.get_hist(
        symbol   = cfg['symbol'],
        exchange = cfg['exchange'],
        interval = cfg['interval'],
        n_bars   = cfg['n_bars']
    )
    data = data[['open', 'high', 'low', 'close', 'volume']].dropna().copy()
    print(f"✅ Fetched {len(data)} bars — {cfg['symbol']} @ {cfg['exchange']}")
    return data


# ══════════════════════════════════════════
# ── 2. HEIKIN ASHI
# ══════════════════════════════════════════
def compute_heikin_ashi(data: pd.DataFrame) -> pd.DataFrame:
    """Add HA OHLC columns to dataframe (vectorized)."""
    df = data.copy()
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4

    ha_open_seed   = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
    df['ha_open']  = (
        df['ha_close']
        .shift(1)
        .fillna(ha_open_seed)
        .ewm(span=2, adjust=False, min_periods=1)
        .mean()
    )
    df['ha_high']  = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low']   = df[['low',  'ha_open', 'ha_close']].min(axis=1)
    return df


# ══════════════════════════════════════════
# ── 3. INDICATORS
# ══════════════════════════════════════════
def compute_indicators(data: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Add EMA20, Volume SMA, and RSI to dataframe."""
    df = data.copy()

    # EMA 20 on HA close
    df['ema20']   = df['ha_close'].ewm(span=cfg['ema_span'], adjust=False).mean()

    # Volume SMA
    df['vol_sma'] = df['volume'].rolling(cfg['vol_sma_period']).mean()

    # RSI (14) on regular close
    delta       = df['close'].diff()
    gain        = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss        = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df['rsi']   = 100 - (100 / (1 + gain / loss))

    return df


# ══════════════════════════════════════════
# ── 4. SIGNALS
# ══════════════════════════════════════════
def compute_signals(data: pd.DataFrame) -> pd.DataFrame:
    """Add buy_signal and sell_signal columns (vectorized)."""
    df = data.copy()

    prev_ha  = df['ha_close'].shift(1)
    prev_ema = df['ema20'].shift(1)

    bull_cross = (df['ha_close'] > df['ema20']) & (prev_ha <= prev_ema)
    bear_cross = (df['ha_close'] < df['ema20']) & (prev_ha >= prev_ema)
    vol_ok     = df['volume'] >= df['vol_sma'] * 0.8
    ha_green   = df['ha_close'] > df['ha_open']
    ha_red     = df['ha_close'] < df['ha_open']

    df['buy_signal']  = bull_cross & ha_green & vol_ok
    df['sell_signal'] = bear_cross & ha_red   & vol_ok

    print(f"✅ Signals — Buys: {df['buy_signal'].sum()}  |  Sells: {df['sell_signal'].sum()}")
    return df


# ══════════════════════════════════════════
# ── 5. TRADE ENGINE (SL / TP)
# ══════════════════════════════════════════
def run_backtest(data: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Simulate trades with SL / TP / Signal exits.
    Exit priority: TP → SL → Signal
    Returns trades DataFrame.
    """
    SL_PCT = cfg['sl_pct']
    TP_PCT = cfg['tp_pct']

    trades   = []
    position = None

    for time, row in data.iterrows():

        if row['buy_signal'] and position is None:
            ep       = row['close']
            position = {
                'entry_time':  time,
                'entry_price': ep,
                'sl':          round(ep * (1 - SL_PCT), 2),
                'tp':          round(ep * (1 + TP_PCT), 2),
            }

        elif position is not None:
            exit_price = exit_reason = None

            if   row['ha_high'] >= position['tp']:  exit_price, exit_reason = position['tp'],  'TP Hit'
            elif row['ha_low']  <= position['sl']:  exit_price, exit_reason = position['sl'],  'SL Hit'
            elif row['sell_signal']:                exit_price, exit_reason = row['close'],    'Signal Exit'

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
    print(f"✅ Backtest complete — {len(trades_df)} trades")
    return trades_df


# ══════════════════════════════════════════
# ── 6. SUMMARY
# ══════════════════════════════════════════
def build_summary(trades_df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Compute performance summary from trades."""
    if len(trades_df) == 0:
        print("⚠️  No trades to summarise.")
        return pd.DataFrame()

    wins   = trades_df['Result'].eq('Win')
    losses = trades_df['Result'].eq('Loss')

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
        'SL %':          f"{cfg['sl_pct'] * 100}%",
        'TP %':          f"{cfg['tp_pct'] * 100}%",
    }])

    print("\n── Summary ──")
    print(summary.T.to_string())
    return summary


# ══════════════════════════════════════════
# ── 7. GOOGLE SHEETS EXPORT
# ══════════════════════════════════════════
def connect_sheets(cfg: dict):
    """Authorize and open Google Sheet."""
    gc = pygsheets.authorize(service_file=cfg['service_account'])
    sh = gc.open(cfg['spreadsheet'])
    print(f"✅ Connected: {sh.title}")
    return sh


def write_sheet(sh, df: pd.DataFrame, title: str):
    """Write DataFrame to named sheet tab (creates tab if missing)."""
    try:
        wks = sh.worksheet_by_title(title)
    except pygsheets.WorksheetNotFound:
        wks = sh.add_worksheet(title)

    wks.clear('A1', None, '*')
    df_out         = df.copy().reset_index(drop=True)
    df_out.columns = df_out.columns.astype(str)
    wks.set_dataframe(df_out, (1, 1), copy_index=False, copy_head=True, fit=True)
    wks.frozen_rows = 1
    print(f"✅ '{title}' → {len(df_out)} rows")
    return wks


def export_to_sheets(sh, data: pd.DataFrame, trades_df: pd.DataFrame, summary: pd.DataFrame):
    """Export HA data, trades, and summary to Google Sheets."""
    # Tab 1 — HA Data
    export_df       = data[['open','high','low','close','volume',
                             'ha_open','ha_high','ha_low','ha_close',
                             'ema20','rsi','buy_signal','sell_signal']].copy()
    export_df.index = export_df.index.astype(str)
    export_df       = export_df.reset_index()
    write_sheet(sh, export_df, "HA_Data")

    # Tab 2 — Trades
    if len(trades_df) > 0:
        t = trades_df.copy()
        t['Entry Time'] = t['Entry Time'].astype(str)
        t['Exit Time']  = t['Exit Time'].astype(str)
        write_sheet(sh, t, "Trades")

    # Tab 3 — Summary
    if len(summary) > 0:
        write_sheet(sh, summary, "Summary")

    print(f"\n🔗 {sh.url}")


# ══════════════════════════════════════════
# ── 8. CHART
# ══════════════════════════════════════════
def build_chart(data: pd.DataFrame, trades_df: pd.DataFrame, cfg: dict):
    """Build and display Plotly chart with HA candles, EMA, signals, SL/TP."""
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.60, 0.20, 0.20],
        vertical_spacing=0.02,
        subplot_titles=('', 'RSI (14)', 'Volume')
    )

    # HA Candles
    fig.add_trace(go.Candlestick(
        x=data.index, open=data['ha_open'], high=data['ha_high'],
        low=data['ha_low'], close=data['ha_close'], name='HA BTCUSD',
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)

    # EMA 20
    fig.add_trace(go.Scatter(
        x=data.index, y=data['ema20'], name='EMA 20',
        line=dict(color='#f7c948', width=1.8)
    ), row=1, col=1)

    # Buy / Sell markers
    buys  = data[data['buy_signal']]
    sells = data[data['sell_signal']]
    fig.add_trace(go.Scatter(
        x=buys.index, y=buys['ha_low'] * 0.999, mode='markers', name='Buy',
        marker=dict(symbol='triangle-up', color='#26a69a', size=12)
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=sells.index, y=sells['ha_high'] * 1.001, mode='markers', name='Sell',
        marker=dict(symbol='triangle-down', color='#ef5350', size=12)
    ), row=1, col=1)

    # SL / TP lines (single trace each using None breaks)
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

    # RSI
    fig.add_trace(go.Scatter(x=data.index, y=data['rsi'], name='RSI',
        line=dict(color='#f7c948', width=1.2)), row=2, col=1)
    fig.add_hline(y=70, line_dash='dot', line_color='#ef5350', row=2, col=1)
    fig.add_hline(y=30, line_dash='dot', line_color='#26a69a', row=2, col=1)

    # Volume
    fig.add_trace(go.Bar(x=data.index, y=data['volume'], name='Volume',
        marker_color='#888888'), row=3, col=1)

    fig.update_layout(
        title    = f"{cfg['symbol']} 5-Min | Heikin Ashi + EMA {cfg['ema_span']} | SL {cfg['sl_pct']*100}% / TP {cfg['tp_pct']*100}%",
        template = 'plotly_dark',
        height   = 800,
        xaxis_rangeslider_visible = False,
        hovermode = 'x unified',
        xaxis     = dict(type='category', nticks=10, tickangle=-45)
    )
    fig.update_yaxes(title_text='Price',  row=1, col=1)
    fig.update_yaxes(title_text='RSI',    row=2, col=1, range=[0, 100])
    fig.update_yaxes(title_text='Volume', row=3, col=1)
    fig.show()


# ══════════════════════════════════════════
# ── MAIN — orchestrates everything
# ══════════════════════════════════════════
def main():
    # 1. Sheets connection
    sh = connect_sheets(CONFIG)

    # 2. Data pipeline
    data = fetch_data(CONFIG)
    data = compute_heikin_ashi(data)
    data = compute_indicators(data, CONFIG)
    data = compute_signals(data)

    # 3. Backtest
    trades_df = run_backtest(data, CONFIG)

    # 4. Summary
    summary = build_summary(trades_df, CONFIG)

    # 5. Export
    export_to_sheets(sh, data, trades_df, summary)

    # 6. Chart
    build_chart(data, trades_df, CONFIG)


if __name__ == '__main__':
    main()