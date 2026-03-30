# ==========================================
# ⚡ OPTIONS TERMINAL v5.0
# ALL instruments in grid layout (like crypto dashboard)
# No CSS injection errors | Dark theme throughout
# ==========================================

import streamlit as st
from kiteconnect import KiteConnect
import pandas as pd
import ta
from datetime import datetime, time as dtime
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pytz
import feedparser
import time as time_module
import numpy as np

API_KEY      = "zirmcjssldz9okdc"
ACCESS_TOKEN = "UqZWDyzibbxw4LByYqBanRflsegXymq8"

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

INITIAL_CAPITAL = 12000
ALL_SYMBOLS     = ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"]

st.set_page_config(layout="wide", page_title="⚡ Options Terminal", page_icon="⚡")
st_autorefresh(interval=60000, key="auto_refresh")

# JS: forcefully zero out Streamlit's inline padding-top on .main (CSS !important can't override inline styles)
st.markdown("""
<script>
(function removePadding() {
    function fix() {
        var main = window.parent.document.querySelector('.main');
        if (main) main.style.paddingTop = '0px';
        var app = window.parent.document.querySelector('.stApp');
        if (app) app.style.paddingTop = '0px';
        var header = window.parent.document.querySelector('header[data-testid="stHeader"]');
        if (header) { header.style.display = 'none'; header.style.height = '0px'; }
    }
    fix();
    setTimeout(fix, 100);
    setTimeout(fix, 500);
    setTimeout(fix, 1000);
})();
</script>
""", unsafe_allow_html=True)

# ── SESSION STATE ─────────────────────
for k, v in {
    "trade_history": [], "open_trades": {},
    "capital": float(INITIAL_CAPITAL), "total_pnl": 0.0,
    "wins": 0, "losses": 0, "trades_today": 0
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── CSS ───────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Syne:wght@700;800&display=swap');

html, body, .stApp { background: #090d17 !important; font-family: 'JetBrains Mono', monospace; padding-top: 0 !important; margin-top: 0 !important; }

/* Kill every source of top gap — covers Streamlit 1.x and 1.3x+ */
header[data-testid="stHeader"]    { display: none !important; height: 0 !important; min-height: 0 !important; }
div[data-testid="stToolbar"]      { display: none !important; height: 0 !important; }
div[data-testid="stDecoration"]   { display: none !important; height: 0 !important; }
div[data-testid="stStatusWidget"] { display: none !important; height: 0 !important; }
#MainMenu                         { display: none !important; }
footer                            { display: none !important; }
.stDeployButton                   { display: none !important; }

/* The actual gap: Streamlit adds padding-top to .main equal to header height (~3.75rem) */
.main                             { padding-top: 0 !important; }
.main > div                       { padding-top: 0 !important; }
.stApp > div                      { padding-top: 0 !important; }

/* Main container */
.main .block-container {
    padding: 0.4rem 0.6rem 0.6rem 0.6rem !important;
    max-width: 100% !important;
    margin-top: 0 !important;
}

section[data-testid="stSidebarContent"] { padding-top: 0.5rem !important; }

/* Remove gaps between streamlit elements */
.element-container { margin-bottom: 0 !important; padding: 0 !important; }
.stMarkdown { margin-bottom: 0 !important; }
.stPlotlyChart { margin-bottom: 0 !important; }
.stButton { margin-bottom: 0 !important; }
div[data-testid="column"] { padding: 0 0.2rem !important; }
div[data-testid="stHorizontalBlock"] { gap: 0.4rem !important; }

/* Sidebar */
[data-testid="stSidebar"] { background: #0d1423 !important; border-right: 1px solid #1a2540; }
[data-testid="stSidebar"] * { color: #dde4f0 !important; font-family: 'JetBrains Mono', monospace !important; }
[data-testid="stSidebar"] label { font-size: 0.6rem !important; color: #4a5568 !important; text-transform: uppercase; letter-spacing: 0.1em; }
[data-testid="stSidebar"] .stSelectbox > div > div,
[data-testid="stSidebar"] .stMultiSelect > div > div { background: #101828 !important; border-color: #1a2540 !important; }

[data-testid="metric-container"] {
    background: #101828 !important; border: 1px solid #1a2540 !important;
    border-radius: 7px !important; padding: 0.55rem 0.8rem !important;
}
[data-testid="metric-container"] label { font-size: 0.56rem !important; color: #4a5568 !important; text-transform: uppercase; letter-spacing: 0.1em; }
[data-testid="metric-container"] [data-testid="metric-value"] { font-size: 0.95rem !important; font-weight: 700 !important; color: #dde4f0 !important; }
[data-testid="stMetricDelta"] { font-size: 0.65rem !important; }

.stButton > button {
    background: transparent !important; border: 1px solid #00c8f0 !important;
    color: #00c8f0 !important; font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem !important; border-radius: 5px !important;
    padding: 0.2rem 0.6rem !important; transition: all 0.15s !important;
}
.stButton > button:hover { background: #00c8f0 !important; color: #090d17 !important; }

/* Dark dataframes */
[data-testid="stDataFrame"] { background: #0d1423 !important; border-radius: 7px !important; }
[data-testid="stDataFrame"] table { background: #0d1423 !important; }
[data-testid="stDataFrame"] th { background: #101828 !important; color: #4a5568 !important; font-size: 0.62rem !important; border-color: #1a2540 !important; }
[data-testid="stDataFrame"] td { background: #0d1423 !important; color: #dde4f0 !important; font-size: 0.68rem !important; border-color: #1a2540 !important; }
[data-testid="stDataFrame"] tr:hover td { background: #101828 !important; }
.dvn-scroller { background: #0d1423 !important; }

/* Expanders */
details summary { background: #101828 !important; border: 1px solid #1a2540 !important; border-radius: 6px !important; color: #4a5568 !important; font-size: 0.7rem !important; padding: 0.35rem 0.8rem !important; }
details > div { background: #0d1423 !important; border: 1px solid #1a2540 !important; border-top: none !important; }
details { margin-bottom: 0.25rem !important; }

.stSuccess { background: #00e67611 !important; border: 1px solid #00e67633 !important; color: #00e676 !important; font-size: 0.75rem !important; border-radius: 6px !important; }
.stWarning { background: #ffc10711 !important; border: 1px solid #ffc10733 !important; font-size: 0.75rem !important; border-radius: 6px !important; }
.stError   { background: #ff3d5711 !important; border: 1px solid #ff3d5733 !important; color: #ff3d57 !important; font-size: 0.75rem !important; border-radius: 6px !important; }
.stInfo    { background: #00c8f011 !important; border: 1px solid #00c8f033 !important; color: #00c8f0 !important; font-size: 0.75rem !important; border-radius: 6px !important; }

.stNumberInput input, .stTextInput input {
    background: #101828 !important; border-color: #1a2540 !important;
    color: #dde4f0 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 0.8rem !important;
}
.stSlider > div > div > div { background: #1a2540 !important; }
.stRadio label, .stCheckbox label { font-size: 0.72rem !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #090d17; }
::-webkit-scrollbar-thumb { background: #1a2540; border-radius: 3px; }

@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def load_instruments():
    nse = pd.DataFrame(kite.instruments("NSE"))
    bse = pd.DataFrame(kite.instruments("BSE"))
    nfo = pd.DataFrame(kite.instruments("NFO"))
    bfo = pd.DataFrame(kite.instruments("BFO"))
    return pd.concat([nse, bse, nfo, bfo], ignore_index=True)

instruments = load_instruments()

_token_cfg = {
    "NIFTY":     ("NIFTY 50",         "INDICES",  "NSE"),
    "SENSEX":    ("SENSEX",            "INDICES",  "BSE"),
    "BANKNIFTY": ("NIFTY BANK",        "INDICES",  "NSE"),
    "FINNIFTY":  ("NIFTY FIN SERVICE", "INDICES",  "NSE"),
}

def get_token(symbol):
    name, seg, exch = _token_cfg[symbol]
    # Filter by exchange column if available, else fallback to segment only
    if "exchange" in instruments.columns:
        df = instruments[
            (instruments["name"] == name) &
            (instruments["segment"] == seg) &
            (instruments["exchange"] == exch)
        ]
    else:
        df = instruments[
            (instruments["name"] == name) &
            (instruments["segment"] == seg)
        ]
    if df.empty:
        return None
    return int(df.iloc[0]["instrument_token"])

@st.cache_data(ttl=55)
def get_data(token_int, sym_name, tf, days):
    # sym_name is included so cache key is unique per symbol
    now = datetime.now()
    from_date = now - pd.Timedelta(days=days)
    for attempt in range(3):
        try:
            data = kite.historical_data(token_int, from_date, now, tf)
            df = pd.DataFrame(data)
            if not df.empty:
                df.set_index("date", inplace=True)
            return df
        except Exception:
            if attempt < 2:
                time_module.sleep(2 ** attempt)
            else:
                return pd.DataFrame()
    return pd.DataFrame()

def apply_indicators(df):
    if df.empty or len(df) < 10:
        return df
    df = df.copy()
    df["EMA9"]  = ta.trend.ema_indicator(df["close"], 9)
    df["EMA21"] = ta.trend.ema_indicator(df["close"], 21)
    df["EMA20"] = ta.trend.ema_indicator(df["close"], 20)
    df["EMA50"] = ta.trend.ema_indicator(df["close"], 50)
    df["RSI"]   = ta.momentum.rsi(df["close"], 14)
    _m = ta.trend.MACD(df["close"])
    df["MACD"]      = _m.macd()
    df["MACD_SIG"]  = _m.macd_signal()
    df["MACD_HIST"] = _m.macd_diff()
    idx = df.index
    dk = idx.normalize() if (hasattr(idx, "tz") and idx.tz) else pd.to_datetime(idx).normalize()
    df["_dk"]    = dk
    df["_cv"]    = df["close"] * df["volume"]
    df["_cumv"]  = df.groupby("_dk")["volume"].cumsum()
    df["_cumpv"] = df.groupby("_dk")["_cv"].cumsum()
    df["VWAP"]   = df["_cumpv"] / df["_cumv"]
    df.drop(columns=["_dk", "_cv", "_cumv", "_cumpv"], inplace=True)
    try:
        if len(df) > 30:
            _a = ta.trend.ADXIndicator(df["high"], df["low"], df["close"])
            df["ADX"] = _a.adx()
            df["+DI"] = _a.adx_pos()
            df["-DI"] = _a.adx_neg()
        else:
            df["ADX"] = df["+DI"] = df["-DI"] = 0.0
    except Exception:
        df["ADX"] = df["+DI"] = df["-DI"] = 0.0
    prev = df["EMA9"].shift(1) - df["EMA21"].shift(1)
    curr = df["EMA9"] - df["EMA21"]
    df["ema_cross"] = 0
    df.loc[(prev < 0) & (curr >= 0), "ema_cross"] =  1
    df.loc[(prev > 0) & (curr <= 0), "ema_cross"] = -1
    return df

_opt_cfg = {
    "SENSEX":    ("BFO", "BFO-OPT", "SENSEX"),
    "BANKNIFTY": ("NFO", "NFO-OPT", "BANKNIFTY"),
    "FINNIFTY":  ("NFO", "NFO-OPT", "FINNIFTY"),
    "NIFTY":     ("NFO", "NFO-OPT", "NIFTY"),
}

@st.cache_data(ttl=55)
def get_option_chain(symbol, price):
    exch, seg, name = _opt_cfg.get(symbol, ("NFO", "NFO-OPT", "NIFTY"))
    price = round(price, -1)  # round to nearest 10 for better cache hits
    try:
        # Use already-loaded instruments filtered by exchange
        exch_instruments = instruments[instruments["exchange"] == exch].copy() if "exchange" in instruments.columns else pd.DataFrame(kite.instruments(exch))
        expiry = exch_instruments[(exch_instruments["name"] == name) & (exch_instruments["segment"] == seg)]["expiry"].min()
        df = exch_instruments[(exch_instruments["name"] == name) & (exch_instruments["expiry"] == expiry)].copy()
        df["diff"] = abs(df["strike"] - price)
        df = df.sort_values("diff").head(30)
        quotes = kite.quote([f"{exch}:{x}" for x in df["tradingsymbol"]])
        rows = []
        for _, r in df.iterrows():
            q = quotes.get(f"{exch}:{r['tradingsymbol']}", {})
            rows.append({
                "symbol": r["tradingsymbol"],
                "strike": r["strike"],
                "type":   r["instrument_type"],
                "ltp":    q.get("last_price", 0),
                "oi":     q.get("oi", 0),
                "volume": q.get("volume", 0),
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()

def calc_pcr(opt):
    if opt.empty: return 1.0
    ce = opt[opt["type"] == "CE"]["oi"].sum()
    pe = opt[opt["type"] == "PE"]["oi"].sum()
    return round(pe / ce, 2) if ce else 1.0

def calc_sr(df, window=20):
    if df.empty or len(df) < window: return None, None
    return (round(df["low"].rolling(window).min().iloc[-1], 2),
            round(df["high"].rolling(window).max().iloc[-1], 2))

def calc_oi_levels(opt):
    if opt.empty or "type" not in opt.columns: return None, None
    pe = opt[opt["type"] == "PE"]
    ce = opt[opt["type"] == "CE"]
    s = pe.loc[pe["oi"].idxmax(), "strike"] if not pe.empty and pe["oi"].sum() > 0 else None
    r = ce.loc[ce["oi"].idxmax(), "strike"] if not ce.empty and ce["oi"].sum() > 0 else None
    return s, r

def smart_money(opt):
    if opt.empty: return "— No Data"
    ce_oi = opt[opt["type"] == "CE"]["oi"].sum()
    pe_oi = opt[opt["type"] == "PE"]["oi"].sum()
    pcr = pe_oi / ce_oi if ce_oi else 0
    if pcr > 1.2: return "FII Bull — Put Writing"
    if pcr < 0.8: return "FII Bear — Call Writing"
    if pcr > 1.1: return "Mild Bullish"
    if pcr < 0.9: return "Mild Bearish"
    return "Neutral"

# ── SIGNAL ENGINE (unchanged logic) ──
def compute_signal(df5, df15, adx_threshold, min_score, signal_mode):
    if df5.empty or len(df5) < 5:
        return "WAIT", 0, ["No 5m data"]
    if df15.empty or len(df15) < 5:
        return "WAIT", 0, ["No 15m data"]
    l5  = df5.iloc[-1]; l15 = df15.iloc[-1]
    adx = l5["ADX"]; rsi = l5["RSI"]
    di_plus = l5["+DI"]; di_minus = l5["-DI"]
    ema9_15 = l15["EMA9"]; ema21_15 = l15["EMA21"]; close15 = l15["close"]
    close5 = l5["close"]; vwap5 = l5["VWAP"]

    if adx < adx_threshold:
        return "WAIT", 0, [f"ADX {round(adx,1)} < {adx_threshold} — flat market"]

    bull_state   = ema9_15 > ema21_15; bear_state = ema9_15 < ema21_15
    bull_cross   = (df15["ema_cross"].tail(6) == 1).any()
    bear_cross   = (df15["ema_cross"].tail(6) == -1).any()
    adx_credit   = 15 if adx >= 25 else 0
    adx_lbl      = f"ADX {round(adx,1)} {'trending' if adx>=25 else '— blocked'}"

    def score_dir(state, cross, candle_ok, di_ok, rsi_ext, vwap_ok, macd_ok):
        if not state and not (signal_mode == "Fresh Cross Only" and cross):
            return 0, []
        sc, rs = 0, []
        if state:             sc += 25; rs.append("EMA9/21 aligned")
        if cross:             sc += 20; rs.append("Fresh EMA cross")
        if candle_ok:         sc += 12; rs.append("Candle confirms")
        if di_ok:             sc += 20; rs.append("DI direction ok")
        if rsi_ext:           sc += 15; rs.append(f"RSI extreme {round(rsi,1)}")
        if vwap_ok:           sc += 10; rs.append("VWAP aligned")
        if macd_ok:           sc += 5;  rs.append("MACD confirms")
        sc += adx_credit;     rs.append(adx_lbl)
        return sc, rs

    call_sc, call_rs = score_dir(
        bull_state, bull_cross,
        close15 > ema9_15,
        di_plus > di_minus,
        rsi > 70,
        close5 > vwap5,
        l5["MACD_HIST"] > 0
    )
    put_sc, put_rs = score_dir(
        bear_state, bear_cross,
        close15 < ema9_15,
        di_minus > di_plus,
        rsi < 30,
        close5 < vwap5,
        l5["MACD_HIST"] < 0
    )

    if signal_mode == "Fresh Cross Only":
        if call_sc >= min_score and not bull_cross: return "WAIT", call_sc, ["Score met, no fresh cross"]
        if put_sc  >= min_score and not bear_cross: return "WAIT", put_sc,  ["Score met, no fresh cross"]

    if call_sc >= min_score and call_sc > put_sc:
        return "CALL", min(call_sc, 100), call_rs
    if put_sc >= min_score and put_sc > call_sc:
        return "PUT",  min(put_sc,  100), put_rs

    best = max(call_sc, put_sc)
    msgs = []
    if call_sc > 0: msgs.append(f"Bull {call_sc}/{min_score}")
    if put_sc  > 0: msgs.append(f"Bear {put_sc}/{min_score}")
    if not msgs: msgs = ["No EMA alignment"]
    return "WAIT", best, msgs

def pick_options(option_df, signal, price, step, capital, lot_size):
    if signal == "WAIT" or option_df.empty: return None, None, None
    opt_type = "CE" if signal == "CALL" else "PE"
    df = option_df[option_df["type"] == opt_type].copy()
    if df.empty: return None, None, None
    atm = round(price / step) * step
    itm = atm - step if signal == "CALL" else atm + step
    otm = atm + step if signal == "CALL" else atm - step
    def build(strike):
        r = df[df["strike"] == strike]
        if r.empty: return None
        row = r.iloc[0].to_dict()
        ltp = float(row["ltp"])
        if ltp <= 0: return None
        cost = round(ltp * lot_size, 2)
        row.update({"cost": cost, "lots": int(capital // cost) if cost > 0 else 0,
                    "sl": round(ltp * 0.70, 2), "t1": round(ltp * 1.50, 2), "t2": round(ltp * 2.00, 2)})
        return row
    return build(atm), build(itm), build(otm)

# ── PAPER TRADING ─────────────────────
def open_trade(symbol, signal, strike, opt_type, ltp, lot_size):
    st.session_state.open_trades[symbol] = {
        "side": signal, "strike": strike, "type": opt_type,
        "entry": ltp, "sl": round(ltp*0.70,2), "t1": round(ltp*1.50,2),
        "lot_size": lot_size, "time": datetime.now().strftime("%H:%M")
    }
    st.session_state.trades_today += 1

def close_trade(symbol, cur_ltp):
    t = st.session_state.open_trades.pop(symbol, None)
    if not t: return 0
    pnl = round((cur_ltp - t["entry"]) * t["lot_size"], 2)
    st.session_state.capital   += pnl
    st.session_state.total_pnl += pnl
    if pnl >= 0: st.session_state.wins   += 1
    else:        st.session_state.losses += 1
    st.session_state.trade_history.append({
        "Time": datetime.now().strftime("%H:%M"), "Symbol": symbol,
        "Side": t["side"], "Strike": t["strike"], "Type": t["type"],
        "Entry": t["entry"], "Exit": cur_ltp, "PnL": pnl, "_paper": True
    })
    return pnl

@st.cache_data(ttl=300)
def fetch_news(kw):
    try:
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={kw.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        return [{"title": e.title, "link": e.link, "time": e.get("published","")[:16]}
                for e in feed.entries[:12]]
    except Exception:
        return []

# ── PLOTLY CHART ─────────────────────
PLOT_BG   = "#090d17"
PLOT_CARD = "#0d1423"
PLOT_GRID = "#1a2540"
PLOT_FONT = "#4a5568"

def make_chart(df5, df15, title):
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.60, 0.22, 0.18],
        vertical_spacing=0.02,
    )
    # Candles
    fig.add_trace(go.Candlestick(
        x=df5.index, open=df5["open"], high=df5["high"], low=df5["low"], close=df5["close"],
        increasing=dict(line=dict(color="#00e676", width=1), fillcolor="rgba(0,230,118,0.3)"),
        decreasing=dict(line=dict(color="#ff3d57", width=1), fillcolor="rgba(255,61,87,0.3)"),
        name="Price", showlegend=False,
    ), row=1, col=1)
    # EMAs
    for col_n, clr, w in [("EMA9","#ffc107",1.5),("EMA21","#00c8f0",1.5),("EMA50","#9c6fff",1)]:
        if col_n in df5.columns:
            fig.add_trace(go.Scatter(x=df5.index, y=df5[col_n], name=col_n,
                line=dict(color=clr, width=w), opacity=0.9), row=1, col=1)
    # VWAP
    fig.add_trace(go.Scatter(x=df5.index, y=df5["VWAP"], name="VWAP",
        line=dict(color="#ff6b6b", width=1.2, dash="dot"), opacity=0.85), row=1, col=1)
    # 15m crosses on 5m chart
    if not df15.empty and "ema_cross" in df15.columns:
        for val, sym_m, clr in [(1,"triangle-up","#00e676"),(-1,"triangle-down","#ff3d57")]:
            c = df15[df15["ema_cross"] == val]
            if not c.empty:
                fig.add_trace(go.Scatter(x=c.index, y=c["close"], mode="markers",
                    name=("Bull X" if val==1 else "Bear X"),
                    marker=dict(symbol=sym_m, size=9, color=clr)), row=1, col=1)
    # MACD
    hist_vals = df5["MACD_HIST"].fillna(0)
    fig.add_trace(go.Bar(x=df5.index, y=hist_vals, name="Hist",
        marker_color=["#00e676" if v >= 0 else "#ff3d57" for v in hist_vals], opacity=0.75,
        showlegend=False), row=2, col=1)
    for col_n, clr in [("MACD","#00c8f0"),("MACD_SIG","#ffc107")]:
        fig.add_trace(go.Scatter(x=df5.index, y=df5[col_n], name=col_n,
            line=dict(color=clr, width=1.2)), row=2, col=1)
    # RSI
    fig.add_trace(go.Scatter(x=df5.index, y=df5["RSI"], name="RSI",
        line=dict(color="#9c6fff", width=1.4), showlegend=False), row=3, col=1)
    for yv, clr in [(70,"#ff3d57"),(30,"#00e676")]:
        fig.add_hline(y=yv, line=dict(color=clr, dash="dot", width=0.8), row=3, col=1)

    # Layout
    fig.update_layout(
        title=dict(text=title, font=dict(family="JetBrains Mono", size=11, color="#4a5568"), x=0.5),
        height=360, paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_CARD,
        margin=dict(l=45, r=8, t=22, b=8),
        font=dict(family="JetBrains Mono", size=9, color=PLOT_FONT),
        legend=dict(orientation="h", y=1.01, x=0, font=dict(size=8), bgcolor="rgba(0,0,0,0)"),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#0d1423", font=dict(family="JetBrains Mono", size=9, color="#dde4f0")),
    )
    for i in range(1, 4):
        fig.update_xaxes(gridcolor=PLOT_GRID, showgrid=True, row=i, col=1,
                         zeroline=False, linecolor=PLOT_GRID, tickfont=dict(size=8))
        fig.update_yaxes(gridcolor=PLOT_GRID, showgrid=True, row=i, col=1,
                         zeroline=False, linecolor=PLOT_GRID, tickfont=dict(size=8))
    return fig


# ══════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<div style='font-family:Syne,sans-serif;font-size:0.95rem;color:#00c8f0;font-weight:800;letter-spacing:0.07em;margin-bottom:0.4rem;'>⚡ CONTROL PANEL</div>", unsafe_allow_html=True)
    st.divider()

    pnl_col  = "#00e676" if st.session_state.total_pnl >= 0 else "#ff3d57"
    pnl_sign = "+" if st.session_state.total_pnl >= 0 else ""
    pnl_pct  = (st.session_state.total_pnl / INITIAL_CAPITAL) * 100
    st.markdown(
        "<div style='font-size:0.58rem;color:#4a5568;text-transform:uppercase;letter-spacing:0.1em;'>Capital</div>"
        f"<div style='font-size:1.2rem;font-weight:700;color:#00c8f0;'>&#8377;{st.session_state.capital:,.0f}</div>"
        f"<div style='font-size:0.78rem;color:{pnl_col};'>{pnl_sign}&#8377;{st.session_state.total_pnl:,.1f} ({pnl_sign}{pnl_pct:.1f}%)</div>",
        unsafe_allow_html=True
    )
    st.divider()

    capital_input = st.number_input("Capital / trade (Rs)", 5000, 500000, INITIAL_CAPITAL, 1000)
    adx_threshold = st.slider("ADX Floor", 15, 30, 25)
    min_score     = st.slider("Min Score", 30, 90, 45)
    signal_mode   = st.radio("Mode", ["Trend + State", "Fresh Cross Only"], index=0)

    st.divider()
    total_t = st.session_state.wins + st.session_state.losses
    wr = (st.session_state.wins / total_t * 100) if total_t > 0 else 0
    st.markdown(
        f"<div style='font-size:0.72rem;'>"
        f"Trades: <span style='color:#00c8f0;'>{total_t}</span> &nbsp;|&nbsp; "
        f"<span style='color:#00e676;'>W:{st.session_state.wins}</span> "
        f"<span style='color:#ff3d57;'>L:{st.session_state.losses}</span><br/>"
        f"Win Rate: <span style='color:#ffc107;'>{wr:.1f}%</span></div>",
        unsafe_allow_html=True
    )
    st.divider()

    if st.button("Reset Paper Account"):
        for k, v in {"capital": float(INITIAL_CAPITAL), "total_pnl": 0.0,
                     "open_trades": {}, "trade_history": [],
                     "wins": 0, "losses": 0, "trades_today": 0}.items():
            st.session_state[k] = v
        st.rerun()


# ══════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════
ist          = pytz.timezone("Asia/Kolkata")
current_time = datetime.now(ist)

if current_time.time() < dtime(9, 15):
    st.warning(f"Market opens 9:15 AM IST. Now: {current_time.strftime('%H:%M:%S')}")
    st.stop()

# ── HEADER ───────────────────────────
pnl_h_col  = "#00e676" if st.session_state.total_pnl >= 0 else "#ff3d57"
pnl_h_sign = "+" if st.session_state.total_pnl >= 0 else ""

st.markdown(
    "<div style='display:flex;align-items:center;justify-content:space-between;"
    "padding:0.6rem 1rem;background:#0d1423;border:1px solid #1a2540;"
    "border-top:2px solid #00c8f0;border-radius:10px;margin-bottom:0.35rem;'>"
    "<div style='display:flex;align-items:center;gap:0.8rem;'>"
    "<span style='font-size:1.2rem;'>&#9889;</span>"
    "<div>"
    "<div style='font-family:Syne,sans-serif;font-size:1rem;font-weight:800;"
    "color:#dde4f0;letter-spacing:0.06em;'>OPTIONS TERMINAL</div>"
    "<div style='font-size:0.56rem;color:#4a5568;'>NIFTY &middot; BANKNIFTY &middot; SENSEX &middot; FINNIFTY &middot; Paper Mode v5.0</div>"
    "</div></div>"
    "<div style='display:flex;gap:1.5rem;align-items:center;'>"
    "<div style='text-align:center;'>"
    "<div style='font-size:0.5rem;color:#4a5568;text-transform:uppercase;'>Status</div>"
    "<div style='font-size:0.72rem;color:#00e676;'>"
    "<span style='display:inline-block;width:6px;height:6px;border-radius:50%;"
    "background:#00e676;animation:blink 2s infinite;margin-right:4px;'></span>LIVE</div>"
    "</div>"
    f"<div style='text-align:center;'><div style='font-size:0.5rem;color:#4a5568;text-transform:uppercase;'>P&amp;L</div>"
    f"<div style='font-size:0.78rem;font-weight:700;color:{pnl_h_col};'>{pnl_h_sign}&#8377;{st.session_state.total_pnl:,.1f}</div></div>"
    f"<div style='text-align:center;'><div style='font-size:0.5rem;color:#4a5568;text-transform:uppercase;'>Trades</div>"
    f"<div style='font-size:0.72rem;color:#dde4f0;'>{st.session_state.trades_today}</div></div>"
    f"<div style='text-align:center;'><div style='font-size:0.5rem;color:#4a5568;text-transform:uppercase;'>Capital</div>"
    f"<div style='font-size:0.78rem;font-weight:700;color:#00c8f0;'>&#8377;{st.session_state.capital:,.0f}</div></div>"
    f"<div style='text-align:center;'><div style='font-size:0.5rem;color:#4a5568;text-transform:uppercase;'>Positions</div>"
    f"<div style='font-size:0.72rem;color:#dde4f0;'>{len(st.session_state.open_trades)}</div></div>"
    f"<div style='font-size:0.56rem;color:#1a2540;'>{current_time.strftime('%d %b %H:%M IST')}</div>"
    "</div></div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div style='background:#ffc10711;border:1px solid #ffc10733;border-radius:6px;"
    "padding:0.3rem 0.9rem;margin-bottom:0.35rem;font-size:0.7rem;color:#ffc107;'>"
    "&#128203; Paper Trading Mode &mdash; Signals &amp; P&amp;L simulated. No real orders placed."
    "</div>",
    unsafe_allow_html=True
)

# ── FETCH ALL DATA UPFRONT ────────────
lot_map  = {"NIFTY":50, "SENSEX":10, "BANKNIFTY":15, "FINNIFTY":40}
step_map = {"NIFTY":50, "SENSEX":100, "BANKNIFTY":100, "FINNIFTY":50}
news_kw  = {"NIFTY":"NIFTY 50 NSE today", "BANKNIFTY":"Bank Nifty today",
             "SENSEX":"SENSEX BSE today", "FINNIFTY":"FINNIFTY NSE today"}

sym_data = {}
with st.spinner("Fetching live market data for all instruments..."):
    for sym in ALL_SYMBOLS:
        tok = get_token(sym)
        if tok is None:
            sym_data[sym] = None
            continue
        df5  = apply_indicators(get_data(tok, sym, "5minute",  3))
        df15 = apply_indicators(get_data(tok, sym, "15minute", 5))
        if df5.empty:
            sym_data[sym] = None
            continue
        price  = df5["close"].iloc[-1]
        opt_df = get_option_chain(sym, price)
        sig, sc, reasons = compute_signal(df5, df15, adx_threshold, min_score, signal_mode)
        atm_row, itm_row, otm_row = pick_options(opt_df, sig, price, step_map[sym], capital_input, lot_map[sym])
        sym_data[sym] = {
            "df5": df5, "df15": df15, "price": price, "opt_df": opt_df,
            "signal": sig, "score": sc, "reasons": reasons,
            "atm_row": atm_row, "itm_row": itm_row, "otm_row": otm_row,
            "pcr": calc_pcr(opt_df), "smart": smart_money(opt_df),
            "support": calc_sr(df5)[0], "resistance": calc_sr(df5)[1],
            "oi_sup": calc_oi_levels(opt_df)[0], "oi_res": calc_oi_levels(opt_df)[1],
        }
        # Auto-log signal
        if sig in ["CALL","PUT"] and atm_row:
            atm_s = round(price / step_map[sym]) * step_map[sym]
            last  = next((t for t in reversed(st.session_state.trade_history)
                         if t.get("Symbol") == sym and "_paper" not in t), None)
            if not last or last.get("Signal") != sig or last.get("Strike") != atm_s:
                st.session_state.trade_history.append({
                    "Time": current_time.strftime("%H:%M"), "Symbol": sym,
                    "Signal": sig, "Strike": atm_s,
                    "Type": "CE" if sig=="CALL" else "PE",
                    "LTP": atm_row["ltp"], "Score": f"{sc}/100",
                })

# ── MAIN GRID + RIGHT PANEL ───────────
main_col, right_col = st.columns([3, 1])

with main_col:
    st.markdown(
        "<div style='font-size:0.58rem;color:#4a5568;text-transform:uppercase;"
        "letter-spacing:0.15em;border-bottom:1px solid #1a2540;padding-bottom:0.2rem;"
        "margin-bottom:0.35rem;'>Index Signal Scorecard &middot; All 4 Instruments</div>",
        unsafe_allow_html=True
    )

    # ── 2-COLUMN GRID: Row1=NIFTY+SENSEX, Row2=BANKNIFTY+FINNIFTY ──
    sym_list = ["NIFTY", "SENSEX", "BANKNIFTY", "FINNIFTY"]
    for i in range(0, len(sym_list), 2):
        cols = st.columns(2)
        for j, sym in enumerate(sym_list[i:i+2]):
            with cols[j]:
                d = sym_data.get(sym)
                if d is None:
                    st.markdown(
                        f"<div style='background:#0d1423;border:1px solid #1a2540;"
                        f"border-radius:10px;padding:1rem;color:#4a5568;font-size:0.75rem;"
                        f"text-align:center;'>&#10060; {sym} — data unavailable</div>",
                        unsafe_allow_html=True
                    )
                    continue

                signal   = d["signal"]
                score    = d["score"]
                price    = d["price"]
                pcr      = d["pcr"]
                atm_row  = d["atm_row"]
                lot_size = lot_map[sym]
                step     = step_map[sym]

                sig_col    = "#00e676" if signal=="CALL" else ("#ff3d57" if signal=="PUT" else "#ffc107")
                bar_color  = "#00e676" if score >= min_score else ("#ffc107" if score >= min_score*0.7 else "#ff3d57")
                bar_pct    = min(int(score), 100)

                rsi_v  = round(d["df5"]["RSI"].iloc[-1], 1)
                adx_v  = round(d["df5"]["ADX"].iloc[-1], 1)
                di_p   = round(d["df5"]["+DI"].iloc[-1], 1)
                di_m   = round(d["df5"]["-DI"].iloc[-1], 1)
                vwap_v = round(d["df5"]["VWAP"].iloc[-1], 2)
                ema_b  = float(d["df15"]["EMA9"].iloc[-1]) > float(d["df15"]["EMA21"].iloc[-1]) if not d["df15"].empty else False
                ema_c  = "#00e676" if ema_b else "#ff3d57"

                # Open trade info
                ot      = st.session_state.open_trades.get(sym)
                ot_html = ""
                if ot:
                    cur_ltp = atm_row["ltp"] if atm_row else ot["entry"]
                    cur_pnl = round((cur_ltp - ot["entry"]) * ot["lot_size"], 2)
                    pc      = "#00e676" if cur_pnl >= 0 else "#ff3d57"
                    ps      = "+" if cur_pnl >= 0 else ""
                    ot_html = (
                        f"<span style='background:#1a2540;padding:0.1rem 0.45rem;border-radius:4px;"
                        f"font-size:0.62rem;color:{pc};margin-left:0.4rem;'>"
                        f"{ot['side']} {ot['strike']}{ot['type']} "
                        f"@ &#8377;{ot['entry']} | {ps}&#8377;{cur_pnl}</span>"
                    )

                # ── CARD ──────────────────────────
                st.markdown(
                    f"<div style='background:#0d1423;border:1px solid #1a2540;"
                    f"border-radius:10px;padding:0.6rem 0.8rem;margin-bottom:0.3rem;'>"
                    f"<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:0.45rem;'>"
                    f"<div style='display:flex;align-items:center;gap:0.55rem;'>"
                    f"<span style='font-family:Syne,sans-serif;font-size:1rem;font-weight:800;color:#dde4f0;'>{sym}</span>"
                    f"<span style='background:{sig_col}22;color:{sig_col};border:1px solid {sig_col}44;"
                    f"padding:0.12rem 0.5rem;border-radius:4px;font-size:0.65rem;font-weight:700;'>{signal}</span>"
                    f"{ot_html}"
                    f"</div>"
                    f"<div style='font-size:1rem;font-weight:700;color:#dde4f0;'>&#8377;{price:,.2f}</div>"
                    f"</div>"
                    f"<div style='display:flex;align-items:center;gap:0.45rem;margin-bottom:0.4rem;'>"
                    f"<span style='font-size:0.56rem;color:#4a5568;'>SCORE</span>"
                    f"<div style='flex:1;height:5px;background:#1a2540;border-radius:3px;overflow:hidden;'>"
                    f"<div style='width:{bar_pct}%;height:100%;background:{bar_color};border-radius:3px;'></div>"
                    f"</div>"
                    f"<span style='font-size:0.65rem;color:{bar_color};font-weight:700;'>{score}/100</span>"
                    f"</div>"
                    f"<div style='display:flex;gap:0.35rem;flex-wrap:wrap;margin-bottom:0.4rem;'>"
                    f"<span style='background:#00c8f022;color:#00c8f0;border:1px solid #00c8f033;"
                    f"padding:0.08rem 0.4rem;border-radius:8px;font-size:0.6rem;'>"
                    f"VWAP {'Abv' if price > vwap_v else 'Blw'}</span>"
                    f"<span style='background:{ema_c}22;color:{ema_c};border:1px solid {ema_c}33;"
                    f"padding:0.08rem 0.4rem;border-radius:8px;font-size:0.6rem;'>"
                    f"{'↑' if ema_b else '↓'} EMA</span>"
                    f"<span style='background:#9c6fff22;color:#9c6fff;border:1px solid #9c6fff33;"
                    f"padding:0.08rem 0.4rem;border-radius:8px;font-size:0.6rem;'>RSI {rsi_v}</span>"
                    f"<span style='background:#ffc10722;color:#ffc107;border:1px solid #ffc10733;"
                    f"padding:0.08rem 0.4rem;border-radius:8px;font-size:0.6rem;'>ADX {adx_v}</span>"
                    f"<span style='background:#00e67622;color:#00e676;border:1px solid #00e67633;"
                    f"padding:0.08rem 0.4rem;border-radius:8px;font-size:0.6rem;'>PCR {pcr}</span>"
                    f"<span style='background:#ff3d5722;color:#ff3d57;border:1px solid #ff3d5733;"
                    f"padding:0.08rem 0.4rem;border-radius:8px;font-size:0.6rem;'>+DI {di_p} -DI {di_m}</span>"
                    f"</div>"
                    f"<div style='display:flex;gap:1.2rem;font-size:0.65rem;color:#9a9eb0;'>"
                    f"<span>S:<b style='color:#00e676;margin-left:3px;'>{d['support']}</b></span>"
                    f"<span>R:<b style='color:#ff3d57;margin-left:3px;'>{d['resistance']}</b></span>"
                    f"<span>OIS:<b style='color:#00e676;margin-left:3px;'>{d['oi_sup']}</b></span>"
                    f"<span>OIR:<b style='color:#ff3d57;margin-left:3px;'>{d['oi_res']}</b></span>"
                    f"<span style='color:#4a5568;'>{d['smart']}</span>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

                # ── CHART ──────────────────────────
                fig = make_chart(d["df5"], d["df15"], f"{sym} (5m)")
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

                # ── TRADE SUGGESTION ───────────────
                if signal == "WAIT":
                    st.info("No trade — conditions not met")
                else:
                    tc1, tc2, tc3 = st.columns(3)
                    for tcol, lbl, row in [(tc1,"ATM",atm_row),(tc2,"ITM",d["itm_row"]),(tc3,"OTM",d["otm_row"])]:
                        with tcol:
                            if row is None:
                                st.markdown(
                                    f"<div style='background:#0d1423;border:1px solid #1a2540;"
                                    f"border-radius:7px;padding:0.55rem;font-size:0.68rem;color:#4a5568;'>"
                                    f"{lbl}: N/A</div>",
                                    unsafe_allow_html=True
                                )
                            else:
                                bc  = "#00e676" if signal=="CALL" else "#ff3d57"
                                ltp = float(row["ltp"])
                                st.markdown(
                                    f"<div style='background:#0d1423;border:1px solid {bc}33;"
                                    f"border-left:3px solid {bc};border-radius:7px;"
                                    f"padding:0.55rem 0.7rem;font-size:0.7rem;'>"
                                    f"<div style='color:{bc};font-weight:700;margin-bottom:0.3rem;'>"
                                    f"{lbl} &mdash; {'CE' if signal=='CALL' else 'PE'}</div>"
                                    f"<div style='color:#9c6fff;font-size:0.6rem;margin-bottom:0.25rem;'>{row['symbol']}</div>"
                                    f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:0.15rem 0.6rem;'>"
                                    f"<div><span style='color:#4a5568;'>Strike</span><br/>"
                                    f"<b style='color:#dde4f0;'>&#8377;{row['strike']}</b></div>"
                                    f"<div><span style='color:#4a5568;'>LTP</span><br/>"
                                    f"<b style='color:#dde4f0;'>&#8377;{round(ltp,2)}</b></div>"
                                    f"<div><span style='color:#4a5568;'>Cost</span><br/>"
                                    f"<b style='color:#ffc107;'>&#8377;{row['cost']}</b></div>"
                                    f"<div><span style='color:#4a5568;'>Lots</span><br/>"
                                    f"<b style='color:#00c8f0;'>{row['lots']}</b></div>"
                                    f"<div><span style='color:#4a5568;'>SL</span><br/>"
                                    f"<b style='color:#ff3d57;'>&#8377;{row['sl']}</b></div>"
                                    f"<div><span style='color:#4a5568;'>T1</span><br/>"
                                    f"<b style='color:#00e676;'>&#8377;{row['t1']}</b></div>"
                                    f"<div style='grid-column:span 2;'><span style='color:#4a5568;'>T2</span>"
                                    f"<b style='color:#00e676;margin-left:6px;'>&#8377;{row['t2']}</b></div>"
                                    f"</div></div>",
                                    unsafe_allow_html=True
                                )

                # ── PAPER TRADE BUTTONS ────────────
                if signal != "WAIT" and atm_row:
                    atm_s    = round(price / step) * step
                    opt_type = "CE" if signal == "CALL" else "PE"
                    ltp_atm  = float(atm_row["ltp"])
                    pb1, pb2, pb3 = st.columns([1,1,2])
                    with pb1:
                        if st.button(f"BUY {sym}", key=f"buy_{sym}"):
                            if sym not in st.session_state.open_trades:
                                open_trade(sym, signal, atm_s, opt_type, ltp_atm, lot_size)
                                st.success(f"Paper {signal} opened @ &#8377;{ltp_atm}")
                                st.rerun()
                            else:
                                st.warning("Position open already!")
                    with pb2:
                        if st.button(f"CLOSE {sym}", key=f"cls_{sym}"):
                            if sym in st.session_state.open_trades:
                                pnl = close_trade(sym, ltp_atm)
                                if pnl >= 0: st.success(f"Closed +&#8377;{pnl}")
                                else:        st.error(f"Closed &#8377;{pnl}")
                                st.rerun()
                            else:
                                st.info("No position.")

                # ── OI HEATMAP + OPTION CHAIN ─────
                with st.expander(f"{sym} — OI Heatmap + Option Chain"):
                    opt_df = d["opt_df"]
                    if not opt_df.empty:
                        # ── Plotly OI Heatmap ──────────────
                        st.markdown(
                            "<div style='font-size:0.62rem;color:#4a5568;text-transform:uppercase;"
                            "letter-spacing:0.1em;margin-bottom:0.3rem;'>&#128293; Open Interest Heatmap</div>",
                            unsafe_allow_html=True
                        )
                        hm_df = opt_df.copy()
                        # pivot: rows=type(CE/PE), cols=strike, values=oi
                        pivot = hm_df.pivot_table(index="type", columns="strike", values="oi", aggfunc="sum").fillna(0)
                        # Sort strikes ascending
                        pivot = pivot[sorted(pivot.columns)]

                        # Build heatmap with Plotly
                        hm_fig = go.Figure(go.Heatmap(
                            z=pivot.values.tolist(),
                            x=[str(int(c)) for c in pivot.columns],
                            y=pivot.index.tolist(),
                            colorscale=[
                                [0.0,  "#0d1423"],
                                [0.3,  "#1a3a5c"],
                                [0.6,  "#0066aa"],
                                [0.8,  "#00c8f0"],
                                [1.0,  "#00e676"],
                            ],
                            showscale=True,
                            colorbar=dict(
                                thickness=8,
                                len=0.8,
                                tickfont=dict(family="JetBrains Mono", size=8, color="#4a5568"),
                                title=dict(text="OI", font=dict(family="JetBrains Mono", size=8, color="#4a5568")),
                            ),
                            hoverongaps=False,
                            hovertemplate="Strike: %{x}<br>Type: %{y}<br>OI: %{z:,.0f}<extra></extra>",
                        ))
                        hm_fig.update_layout(
                            height=160,
                            margin=dict(l=40, r=40, t=8, b=30),
                            paper_bgcolor="#090d17",
                            plot_bgcolor="#0d1423",
                            font=dict(family="JetBrains Mono", size=9, color="#4a5568"),
                            xaxis=dict(
                                title=dict(text="Strike", font=dict(size=9, color="#4a5568")),
                                tickfont=dict(size=8, color="#4a5568"),
                                gridcolor="#1a2540", showgrid=False,
                                tickangle=-45,
                            ),
                            yaxis=dict(
                                title=dict(text="Type", font=dict(size=9, color="#4a5568")),
                                tickfont=dict(size=9, color="#dde4f0"),
                                gridcolor="#1a2540", showgrid=False,
                            ),
                        )
                        st.plotly_chart(hm_fig, use_container_width=True, config={"displayModeBar": False})

                        # ── CE / PE tables side by side ────
                        st.markdown(
                            "<div style='font-size:0.62rem;color:#4a5568;text-transform:uppercase;"
                            "letter-spacing:0.1em;margin:0.4rem 0 0.25rem;'>Option Chain</div>",
                            unsafe_allow_html=True
                        )
                        oa, ob = st.columns(2)
                        with oa:
                            st.markdown("<span style='color:#00e676;font-size:0.65rem;'>&#128217; CE — Calls</span>", unsafe_allow_html=True)
                            ce = opt_df[opt_df["type"]=="CE"].sort_values("strike")[["strike","ltp","oi","volume"]].head(12)
                            st.dataframe(ce, use_container_width=True, hide_index=True)
                        with ob:
                            st.markdown("<span style='color:#ff3d57;font-size:0.65rem;'>&#128218; PE — Puts</span>", unsafe_allow_html=True)
                            pe = opt_df[opt_df["type"]=="PE"].sort_values("strike",ascending=False)[["strike","ltp","oi","volume"]].head(12)
                            st.dataframe(pe, use_container_width=True, hide_index=True)
                    else:
                        st.info("No option chain data")

                # ── REASONING ─────────────────────
                with st.expander(f"{sym} — Signal Reasoning"):
                    for r in d["reasons"]:
                        st.markdown(f"- {r}")

                st.markdown("<hr style='border-color:#1a2540;margin:0.1rem 0 0.3rem;'/>", unsafe_allow_html=True)

# ── RIGHT PANEL ───────────────────────
with right_col:
    # News
    primary_sym = ALL_SYMBOLS[0]
    news_items  = fetch_news(news_kw.get(primary_sym, "NSE India market"))

    st.markdown(
        "<div style='background:#0d1423;border:1px solid #1a2540;border-radius:10px;"
        "padding:0.7rem;margin-bottom:0.6rem;'>"
        "<div style='font-size:0.65rem;font-weight:700;color:#dde4f0;margin-bottom:0.4rem;'>&#128240; Market News</div>",
        unsafe_allow_html=True
    )
    for item in news_items[:8]:
        title = item["title"][:80] + ("..." if len(item["title"]) > 80 else "")
        st.markdown(
            f"<div style='padding:0.35rem 0.55rem;border-bottom:1px solid #1a2540;"
            f"border-left:2px solid #00c8f0;margin-bottom:2px;background:#00c8f005;'>"
            f"<a href='{item['link']}' target='_blank' style='color:#dde4f0;text-decoration:none;"
            f"font-size:0.66rem;line-height:1.4;display:block;'>{title}</a>"
            f"<div style='color:#4a5568;font-size:0.56rem;margin-top:1px;'>{item['time']}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # Open positions
    st.markdown(
        "<div style='font-size:0.56rem;color:#4a5568;text-transform:uppercase;"
        "letter-spacing:0.14em;border-bottom:1px solid #1a2540;padding-bottom:0.2rem;"
        "margin-bottom:0.35rem;'>Open Positions</div>",
        unsafe_allow_html=True
    )
    if st.session_state.open_trades:
        for sym, t in st.session_state.open_trades.items():
            sc = "#00e676" if t["side"]=="CALL" else "#ff3d57"
            st.markdown(
                f"<div style='background:#101828;border:1px solid #1a2540;border-left:3px solid {sc};"
                f"border-radius:5px;padding:0.4rem 0.6rem;margin-bottom:0.3rem;font-size:0.7rem;'>"
                f"<div style='color:{sc};font-weight:700;'>{t['side']} {sym}</div>"
                f"<div style='color:#dde4f0;'>{t['strike']}{t['type']} @ &#8377;{t['entry']}</div>"
                f"<div style='color:#4a5568;font-size:0.6rem;'>SL &#8377;{t['sl']} | T1 &#8377;{t['t1']} | {t['time']}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
    else:
        st.markdown("<div style='font-size:0.7rem;color:#4a5568;text-align:center;padding:0.6rem;'>No open positions</div>", unsafe_allow_html=True)

    # Trade journal
    st.markdown(
        "<div style='font-size:0.56rem;color:#4a5568;text-transform:uppercase;"
        "letter-spacing:0.14em;border-bottom:1px solid #1a2540;padding-bottom:0.2rem;"
        "margin:0.6rem 0 0.35rem;'>Trade Journal</div>",
        unsafe_allow_html=True
    )
    paper = [t for t in st.session_state.trade_history if t.get("_paper")]
    if paper:
        for tr in reversed(paper[-8:]):
            pnl = tr["PnL"]
            pc  = "#00e676" if pnl >= 0 else "#ff3d57"
            ps  = "+" if pnl >= 0 else ""
            st.markdown(
                f"<div style='background:#101828;border:1px solid #1a2540;border-radius:5px;"
                f"padding:0.32rem 0.55rem;margin-bottom:0.25rem;font-size:0.67rem;'>"
                f"<div style='display:flex;justify-content:space-between;'>"
                f"<span style='color:#94a3b8;'>{'W' if pnl>=0 else 'L'} {tr['Symbol']} {tr['Side']}</span>"
                f"<span style='color:{pc};font-weight:700;'>{ps}&#8377;{pnl}</span></div>"
                f"<div style='color:#4a5568;font-size:0.58rem;'>&#8377;{tr['Entry']} &#8594; &#8377;{tr['Exit']} | {tr['Time']}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        # P&L summary
        all_pnl = [t["PnL"] for t in paper]
        tot_c   = "#00e676" if st.session_state.total_pnl >= 0 else "#ff3d57"
        tot_s   = "+" if st.session_state.total_pnl >= 0 else ""
        avg     = sum(all_pnl) / len(all_pnl)
        st.markdown(
            f"<div style='background:#101828;border:1px solid #1a2540;border-radius:7px;"
            f"padding:0.55rem 0.7rem;font-size:0.68rem;margin-top:0.4rem;'>"
            f"<div style='font-size:0.56rem;color:#4a5568;text-transform:uppercase;"
            f"letter-spacing:0.1em;margin-bottom:0.3rem;'>P&amp;L Summary</div>"
            f"<div style='display:flex;justify-content:space-between;margin-bottom:0.18rem;'>"
            f"<span style='color:#4a5568;'>Total</span>"
            f"<span style='color:{tot_c};font-weight:700;'>{tot_s}&#8377;{st.session_state.total_pnl:,.1f}</span></div>"
            f"<div style='display:flex;justify-content:space-between;margin-bottom:0.18rem;'>"
            f"<span style='color:#4a5568;'>Best</span><span style='color:#00e676;'>+&#8377;{max(all_pnl):,.1f}</span></div>"
            f"<div style='display:flex;justify-content:space-between;margin-bottom:0.18rem;'>"
            f"<span style='color:#4a5568;'>Worst</span><span style='color:#ff3d57;'>&#8377;{min(all_pnl):,.1f}</span></div>"
            f"<div style='display:flex;justify-content:space-between;'>"
            f"<span style='color:#4a5568;'>Avg</span>"
            f"<span style='color:{'#00e676' if avg>=0 else '#ff3d57'};'>{'+'  if avg>=0 else ''}&#8377;{avg:,.1f}</span></div>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown("<div style='font-size:0.7rem;color:#4a5568;text-align:center;padding:0.6rem;'>No paper trades yet</div>", unsafe_allow_html=True)

    # Signal log
    sig_logs = [t for t in st.session_state.trade_history if not t.get("_paper")]
    if sig_logs:
        st.markdown(
            "<div style='font-size:0.56rem;color:#4a5568;text-transform:uppercase;"
            "letter-spacing:0.14em;border-bottom:1px solid #1a2540;padding-bottom:0.2rem;"
            "margin:0.6rem 0 0.35rem;'>Signal Log</div>",
            unsafe_allow_html=True
        )
        df_log = pd.DataFrame(sig_logs[-8:]).iloc[::-1][["Time","Symbol","Signal","Strike","Score"]]
        st.dataframe(df_log, use_container_width=True, hide_index=True)
        if st.button("Clear Log"):
            st.session_state.trade_history = []
            st.rerun()

# Footer
st.markdown(
    f"<div style='font-size:0.52rem;color:#1a2540;text-align:center;margin-top:0.8rem;'>"
    f"OPTIONS TERMINAL v5.0 &middot; Paper Mode &middot; Fixed Signal Engine &middot; "
    f"{current_time.strftime('%d %b %Y %H:%M IST')} &middot; Auto-refresh 60s</div>",
    unsafe_allow_html=True
)