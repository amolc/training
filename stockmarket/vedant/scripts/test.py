from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import pygsheets
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tvDatafeed import TvDatafeed, Interval

# ── Config ──
SERVICE_ACCOUNT_FILE = 'credentials.json'
YOUR_GMAIL           = 'trade-610@indigo-history-493211-r4.iam.gserviceaccount.com'   # ← change this
SPREADSHEET_NAME     = 'EMA'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# ─────────────────────────────────────────────────
# ── Auto-create sheet + share to your Gmail ──
# ─────────────────────────────────────────────────
def create_and_share_sheet(creds, title, email='trade-610@indigo-history-493211-r4.iam.gserviceaccount.com'):
    drive_service   = build('drive',  'v3', credentials=creds)
    sheets_service  = build('sheets', 'v4', credentials=creds)

    # Create the spreadsheet
    spreadsheet = sheets_service.spreadsheets().create(body={
        'properties': {'title': title}
    }).execute()

    sheet_id = spreadsheet['spreadsheetId']
    print(f"✅ Sheet created — ID: {sheet_id}")

    # Share it with your personal Gmail as Editor
    drive_service.permissions().create(
        fileId=sheet_id,
        body={
            'type': 'user',
            'role': 'editor',
            'emailAddress': 'trade-610@indigo-history-493211-r4.iam.gserviceaccount.com'
        },
        sendNotificationEmail=False
    ).execute()
    print(f"✅ Shared with {email}")
    return sheet_id

# ── Fetch Data ──
tv = TvDatafeed()
data = tv.get_hist(
    symbol='AAPL',
    exchange='NASDAQ',
    interval=Interval.in_1_minute,
    n_bars=50
)
data = data[['open', 'high', 'low', 'close', 'volume']].dropna()

# ── EMA 3, 9, 21 ──
data['ema3']  = data['close'].ewm(span=3,  adjust=False).mean()
data['ema9']  = data['close'].ewm(span=9,  adjust=False).mean()
data['ema21'] = data['close'].ewm(span=21, adjust=False).mean()

# ── ATR 14 ──
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

data['count_co_ema3_ema9']  = (data['co_ema3_ema9']  != '').cumsum()
data['count_co_ema3_ema21'] = (data['co_ema3_ema21'] != '').cumsum()
data['count_co_ema9_ema21'] = (data['co_ema9_ema21'] != '').cumsum()

# ── Save CSV ──
data.to_csv('AAPL_1min_EMA_crossovers.csv')
print("CSV saved.")

# ── Create Sheet + Share ──
SHEET_ID = create_and_share_sheet(creds, SPREADSHEET_NAME, YOUR_GMAIL)

# ── Connect via pygsheets ──
gc = pygsheets.authorize(custom_credentials=creds)
sh = gc.open_by_key(SHEET_ID)
print(f"Connected to: {sh.title}")

# ── Helper: write dataframe to a tab ──
def write_tab(sh, tab_name, df):
    try:
        wks = sh.worksheet_by_title(tab_name)
    except pygsheets.WorksheetNotFound:
        wks = sh.add_worksheet(tab_name)
    wks.clear('A1', None, '*')
    wks.set_dataframe(df, (1, 1), copy_index=False, copy_head=True, fit=True)
    wks.frozen_rows = 1
    print(f"✅ {tab_name} — {len(df)} rows written.")

# ── Tab 1: Full Data ──
export_df = data.copy()
export_df.index = export_df.index.astype(str)
export_df = export_df.reset_index()
export_df.columns = [str(c) for c in export_df.columns]
write_tab(sh, 'EMA_Data', export_df)

# ── Tab 2: Crossover Events ──
co_df = data[
    (data['co_ema3_ema9']  != '') |
    (data['co_ema3_ema21'] != '') |
    (data['co_ema9_ema21'] != '')
][['close','ema3','ema9','ema21',
   'co_ema3_ema9','co_ema3_ema21','co_ema9_ema21',
   'count_co_ema3_ema9','count_co_ema3_ema21','count_co_ema9_ema21']].copy()
co_df.index = co_df.index.astype(str)
co_df = co_df.reset_index()
co_df.columns = [str(c) for c in co_df.columns]
write_tab(sh, 'Crossover_Events', co_df)

# ── Tab 3: Summary ──
summary = pd.DataFrame({
    'Pair':             ['EMA3×EMA9', 'EMA3×EMA21', 'EMA9×EMA21'],
    'Total_Crossovers': [
        int((data['co_ema3_ema9']  != '').sum()),
        int((data['co_ema3_ema21'] != '').sum()),
        int((data['co_ema9_ema21'] != '').sum()),
    ],
    'Bullish': [
        int(data['co_ema3_ema9'].str.contains('Bullish').sum()),
        int(data['co_ema3_ema21'].str.contains('Bullish').sum()),
        int(data['co_ema9_ema21'].str.contains('Bullish').sum()),
    ],
    'Bearish': [
        int(data['co_ema3_ema9'].str.contains('Bearish').sum()),
        int(data['co_ema3_ema21'].str.contains('Bearish').sum()),
        int(data['co_ema9_ema21'].str.contains('Bearish').sum()),
    ],
})
write_tab(sh, 'Summary', summary)

print(f"\n🔗 Open your sheet: {sh.url}")

# ── Plotly Chart ──
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.75, 0.25], vertical_spacing=0.03)
fig.add_trace(go.Candlestick(
    x=data.index, open=data['open'], high=data['high'],
    low=data['low'], close=data['close'], name='AAPL',
    increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
), row=1, col=1)
for ema, color, width in [('ema3','#f7c948',1.2),('ema9','#4f9cf0',1.5),('ema21','#b06ef7',2.0)]:
    fig.add_trace(go.Scatter(x=data.index, y=data[ema], name=ema.upper(),
        line=dict(color=color, width=width)), row=1, col=1)

def add_markers(fig, data, col, b_sym, s_sym, b_col, s_col, label):
    bull = data[col].str.contains('Bullish', na=False)
    bear = data[col].str.contains('Bearish', na=False)
    fig.add_trace(go.Scatter(x=data[bull].index, y=data[bull]['low']*0.9995,
        mode='markers', name=f'{label} ▲',
        marker=dict(symbol=b_sym, color=b_col, size=10,
                    line=dict(color='white', width=0.5))), row=1, col=1)
    fig.add_trace(go.Scatter(x=data[bear].index, y=data[bear]['high']*1.0005,
        mode='markers', name=f'{label} ▼',
        marker=dict(symbol=s_sym, color=s_col, size=10,
                    line=dict(color='white', width=0.5))), row=1, col=1)

add_markers(fig, data, 'co_ema3_ema9',  'triangle-up','triangle-down','#26a69a','#ef5350','EMA3×9')
add_markers(fig, data, 'co_ema3_ema21', 'star',       'x',            '#a5d6a7','#ef9a9a','EMA3×21')
add_markers(fig, data, 'co_ema9_ema21', 'diamond',    'cross',        '#b06ef7','#f76e6e','EMA9×21')

fig.add_trace(go.Scatter(x=data.index, y=data['atr14'], name='ATR 14',
    line=dict(color='#ffb74d', width=1.2),
    fill='tozeroy', fillcolor='rgba(255,183,77,0.1)'), row=2, col=1)

fig.update_layout(title='AAPL 1-Min | EMA 3/9/21 Crossover',
    xaxis_rangeslider_visible=False, template='plotly_dark', height=700,
    hovermode='x unified', legend=dict(orientation='h', yanchor='bottom', y=1.01))
fig.update_yaxes(title_text='Price', row=1, col=1)
fig.update_yaxes(title_text='ATR',   row=2, col=1)
fig.show()