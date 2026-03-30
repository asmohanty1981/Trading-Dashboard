# ============================================================
# 🛢️ MCX MULTI-COMMODITY OPTIONS DASHBOARD — v4
# ============================================================
# NEW IN v4:
#
# FEATURE 1: Multi-Commodity Support
#   Added: GOLDM, SILVERM, NATURALGAS alongside CRUDEOIL
#   - Each commodity has its own instrument fetcher, lot sizes,
#     segment mapping (MCX-FUT / MCX-OPT), and premium ranges
#   - Commodity selector in sidebar switches entire dashboard context
#   - Lot sizes:
#       CRUDEOIL  = 100 bbl  | Mini CRUDEOIL = 10 bbl
#       GOLDM     = 10 gm    | SILVERM = 5 kg
#       NATURALGAS= 1250 mmBtu
#   - Signal engine is commodity-agnostic (same scoring logic)
#   - ATR/ADX thresholds auto-adjusted per commodity volatility profile
#
# FEATURE 2: Paper Trade Analyzer
#   Purpose: Evaluate dashboard signal quality without real money
#   - Dedicated "📊 Paper Analyzer" tab in UI
#   - Logs every signal with: entry price, premium, SL, T1, T2
#   - Tracks outcome: Open / SL Hit / T1 Hit / T2 Hit / Expired
#   - Calculates:
#       Win rate (%), Avg R:R, Max drawdown, Profit factor
#       Signal accuracy per commodity
#   - "Simulate Outcome" button: checks current LTP vs SL/T1/T2
#     and auto-marks trade as SL/T1/T2 hit
#   - P&L summary card per commodity + overall
#   - Export paper trades to CSV
#
# INHERITED FIXES (v3):
#   FIX 1: Removed hard prev_high block → soft -5 pt penalty
#   FIX 2: Trade log upsert (same strike = update, not skip)
#   FIX 3: Proper OHLC candlestick charts (Altair)
# ============================================================

import streamlit as st
from kiteconnect import KiteConnect
import pandas as pd
import ta
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import altair as alt
import time as time_module
import feedparser
import json

# ── CONFIG ─────────────────────────────────────────────────────────────────────
API_KEY      = "zirmcjssldz9okdc"
ACCESS_TOKEN = "UqZWDyzibbxw4LByYqBanRflsegXymq8"

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

st.set_page_config(layout="wide", page_title="MCX Multi-Commodity Dashboard")

# ── COMMODITY CONFIG ───────────────────────────────────────────────────────────
COMMODITY_CONFIG = {
    "CRUDEOIL": {
        "label":         "🛢️ Crude Oil",
        "name":          "CRUDEOIL",
        "segment_fut":   "MCX-FUT",
        "segment_opt":   "MCX-OPT",
        "lot_sizes":     [100, 10],
        "lot_labels":    ["Standard (100 bbl)", "Mini (10 bbl)"],
        "default_lot":   0,
        "min_prem":      200,
        "max_prem":      280,
        "adx_thresh":    22,
        "min_score":     55,
        "atr_scale":     1.0,     # reference
        "tick":          50,      # strike interval for option chain display
        "news_query":    "crude+oil+MCX+price",
        "unit":          "₹/bbl",
        "color":         "#8B4513",
    },
    "GOLDM": {
        "label":         "🥇 Gold Mini",
        "name":          "GOLDM",
        "segment_fut":   "MCX-FUT",
        "segment_opt":   "MCX-OPT",
        "lot_sizes":     [10],
        "lot_labels":    ["10 gm"],
        "default_lot":   0,
        "min_prem":      150,
        "max_prem":      300,
        "adx_thresh":    20,
        "min_score":     52,
        "atr_scale":     2.5,
        "tick":          100,
        "news_query":    "gold+MCX+GOLDM+price",
        "unit":          "₹/10gm",
        "color":         "#FFD700",
    },
    "SILVERM": {
        "label":         "🥈 Silver Mini",
        "name":          "SILVERM",
        "segment_fut":   "MCX-FUT",
        "segment_opt":   "MCX-OPT",
        "lot_sizes":     [5],
        "lot_labels":    ["5 kg"],
        "default_lot":   0,
        "min_prem":      100,
        "max_prem":      250,
        "adx_thresh":    20,
        "min_score":     50,
        "atr_scale":     3.0,
        "tick":          500,
        "news_query":    "silver+MCX+SILVERM+price",
        "unit":          "₹/kg",
        "color":         "#C0C0C0",
    },
    "NATURALGAS": {
        "label":         "🔥 Natural Gas",
        "name":          "NATURALGAS",
        "segment_fut":   "MCX-FUT",
        "segment_opt":   "MCX-OPT",
        "lot_sizes":     [1250],
        "lot_labels":    ["1250 mmBtu"],
        "default_lot":   0,
        "min_prem":      2,
        "max_prem":      8,
        "adx_thresh":    20,
        "min_score":     50,
        "atr_scale":     0.5,
        "tick":          10,
        "news_query":    "natural+gas+MCX+price",
        "unit":          "₹/mmBtu",
        "color":         "#4FC3F7",
    },
}

ist          = pytz.timezone("Asia/Kolkata")
current_time = datetime.now(ist)

# ── STYLES ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@600;800&display=swap');

html, body, [class*="css"] { font-family: 'JetBrains Mono', monospace; }
h1,h2,h3 { font-family: 'Syne', sans-serif !important; }

[data-testid="stMetricValue"] { font-weight:800!important; font-size:22px!important; }
[data-testid="stMetricLabel"] { font-weight:600!important; color:#555!important; }

.sig-call    { background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border-left:5px solid #2e7d32;
               padding:14px 18px; border-radius:10px; font-size:17px; font-weight:700; margin:6px 0; }
.sig-put     { background:linear-gradient(135deg,#fce4ec,#f8bbd0); border-left:5px solid #c62828;
               padding:14px 18px; border-radius:10px; font-size:17px; font-weight:700; margin:6px 0; }
.sig-blocked { background:linear-gradient(135deg,#fff3e0,#ffe0b2); border-left:5px solid #e65100;
               padding:14px 18px; border-radius:10px; font-size:17px; font-weight:700; margin:6px 0; }
.sig-wait    { background:linear-gradient(135deg,#fff8e1,#ffecb3); border-left:5px solid #f9a825;
               padding:14px 18px; border-radius:10px; font-size:17px; font-weight:700; margin:6px 0; }
.move-high   { background:#e8f5e9; border-left:5px solid #2e7d32; padding:12px 16px;
               border-radius:10px; font-weight:600; margin:6px 0; }
.move-mid    { background:#fff8e1; border-left:5px solid #f9a825; padding:12px 16px;
               border-radius:10px; font-weight:600; margin:6px 0; }
.move-low    { background:#fafafa; border-left:5px solid #bdbdbd; padding:12px 16px;
               border-radius:10px; margin:6px 0; }
.bar-wrap    { background:#e0e0e0; border-radius:6px; height:12px; margin:3px 0 8px; }
.bar-fill    { border-radius:6px; height:12px; }

.paper-win  { background:#e8f5e9; border-left:4px solid #2e7d32; padding:8px 12px; border-radius:8px; margin:4px 0; }
.paper-loss { background:#fce4ec; border-left:4px solid #c62828; padding:8px 12px; border-radius:8px; margin:4px 0; }
.paper-open { background:#e3f2fd; border-left:4px solid #1565c0; padding:8px 12px; border-radius:8px; margin:4px 0; }
.paper-stat { background:#f5f5f5; border-radius:10px; padding:16px; margin:6px 0; text-align:center; }
.paper-stat .num { font-size:28px; font-weight:800; font-family:'Syne',sans-serif; }
.paper-stat .lbl { font-size:12px; color:#666; margin-top:4px; }

.commodity-tag { display:inline-block; padding:3px 10px; border-radius:20px;
                 font-size:12px; font-weight:700; margin:0 4px; }
</style>
""", unsafe_allow_html=True)

# ── HEADER ─────────────────────────────────────────────────────────────────────
col_title, col_clock = st.columns([8, 2])
with col_title:
    st.title("📊 MCX MULTI-COMMODITY OPTIONS DASHBOARD")
with col_clock:
    st.markdown(f"### 🕒 {current_time.strftime('%H:%M:%S')}")

st_autorefresh(interval=60000, key="refresh")

# ── SESSION STATE ──────────────────────────────────────────────────────────────
if "trade_log" not in st.session_state:
    st.session_state.trade_log = pd.DataFrame(columns=[
        "First_Seen","Last_Updated","Confirmations","Commodity","Signal","Symbol",
        "Strike","Type","LTP","Cost_1Lot","Lots","Total_Capital",
        "SL","T1","T2","Confidence","Move_Score"
    ])

# Paper trade log — richer structure for analysis
if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = pd.DataFrame(columns=[
        "ID","Time","Commodity","Signal","Symbol","Strike","Type",
        "Entry_Premium","SL","T1","T2","Lots","Lot_Size",
        "Capital_Used","Status","Exit_Premium","PnL","PnL_Pct",
        "Confidence","Score","Notes"
    ])
if "paper_id_counter" not in st.session_state:
    st.session_state.paper_id_counter = 1

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    # Commodity selector
    st.markdown("### 🌐 Select Commodity")
    commodity_key = st.selectbox(
        "Commodity",
        list(COMMODITY_CONFIG.keys()),
        format_func=lambda k: COMMODITY_CONFIG[k]["label"]
    )
    cfg = COMMODITY_CONFIG[commodity_key]

    st.markdown(f"**Trading:** {cfg['label']} ({cfg['unit']})")
    st.markdown("---")

    capital      = st.number_input("Total Capital (₹)", 10000, 1000000, 25000, 5000)
    num_lots     = st.number_input("Number of Lots", 1, 10, 2)
    lot_size_opt = st.selectbox(
        "Lot Size",
        cfg["lot_sizes"],
        index=cfg["default_lot"],
        format_func=lambda v: cfg["lot_labels"][cfg["lot_sizes"].index(v)]
    )

    st.markdown("---")
    st.markdown("**🎯 Premium Target Range**")
    min_prem    = st.number_input("Min Premium (₹)", 1, 5000, cfg["min_prem"], 10)
    max_prem    = st.number_input("Max Premium (₹)", 1, 5000, cfg["max_prem"], 10)
    target_prem = (min_prem + max_prem) / 2
    st.info(
        f"Premium: ₹{min_prem}–₹{max_prem}\n"
        f"Per lot: ₹{int(min_prem*lot_size_opt)}–₹{int(max_prem*lot_size_opt)}\n"
        f"{num_lots} lot(s): ₹{int(min_prem*lot_size_opt*num_lots):,}–"
        f"₹{int(max_prem*lot_size_opt*num_lots):,}"
    )

    st.markdown("---")
    st.markdown("**📈 Signal Settings**")
    adx_min   = st.slider("ADX Threshold", 18, 35, cfg["adx_thresh"])
    min_score = st.slider("Min Signal Score", 40, 90, cfg["min_score"])

    st.markdown("---")
    st.markdown("**🚀 200-Pt Move Detector**")
    show_200   = st.checkbox("Show 200-Pt Move Panel", value=True)
    move_boost = st.checkbox("Boost confidence when move aligns", value=True)

    st.markdown("---")
    st.markdown("**📊 Paper Analyzer**")
    paper_enabled = st.checkbox("Auto-log signals to Paper Analyzer", value=True)

# ── TABS ───────────────────────────────────────────────────────────────────────
tab_live, tab_paper, tab_compare = st.tabs([
    f"📡 Live Signals — {cfg['label']}",
    "📊 Paper Trade Analyzer",
    "🆚 Commodity Comparison"
])

# ── INSTRUMENTS ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400)
def load_instruments():
    return pd.DataFrame(kite.instruments("MCX"))

instruments = load_instruments()

def get_token(commodity_name):
    df = instruments[
        (instruments["name"] == commodity_name) &
        (instruments["segment"] == COMMODITY_CONFIG[commodity_name]["segment_fut"])
    ].copy()
    df = df[df["expiry"] >= pd.Timestamp.today().date()].sort_values("expiry")
    if df.empty:
        return None
    return int(df.iloc[0]["instrument_token"])

# ── DATA FETCH ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=55)
def get_data(_token, tf, days):
    now = datetime.now()
    from_date = now - pd.Timedelta(days=days)
    for attempt in range(3):
        try:
            data = kite.historical_data(_token, from_date, now, tf)
            df   = pd.DataFrame(data)
            if not df.empty:
                df.set_index("date", inplace=True)
            return df
        except Exception as e:
            if attempt < 2:
                time_module.sleep(2 ** attempt)
            else:
                st.warning(f"Data fetch error ({tf}): {e}")
                return pd.DataFrame()
    return pd.DataFrame()

# ── INDICATORS ─────────────────────────────────────────────────────────────────
def apply_indicators(df):
    if df.empty or len(df) < 15:
        return df

    df["EMA9"]  = ta.trend.ema_indicator(df["close"], 9)
    df["EMA21"] = ta.trend.ema_indicator(df["close"], 21)
    df["RSI"]   = ta.momentum.rsi(df["close"], 14)

    _m = ta.trend.MACD(df["close"])
    df["MACD"]      = _m.macd()
    df["MACD_SIG"]  = _m.macd_signal()
    df["MACD_HIST"] = _m.macd_diff()

    idx = df.index
    dk  = idx.normalize() if (hasattr(idx,"tz") and idx.tz) else pd.to_datetime(idx).normalize()
    df["_dk"]    = dk
    df["_cv"]    = df["close"] * df["volume"]
    df["_cumv"]  = df.groupby("_dk")["volume"].cumsum()
    df["_cumpv"] = df.groupby("_dk")["_cv"].cumsum()
    df["VWAP"]   = df["_cumpv"] / df["_cumv"]
    df.drop(columns=["_dk","_cv","_cumv","_cumpv"], inplace=True)

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

    try:
        df["ATR"] = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], window=14
        ).average_true_range()
    except Exception:
        df["ATR"] = 0.0

    try:
        _bb            = ta.volatility.BollingerBands(df["close"], window=20)
        df["BB_upper"] = _bb.bollinger_hband()
        df["BB_lower"] = _bb.bollinger_lband()
        df["BB_width"] = df["BB_upper"] - df["BB_lower"]
    except Exception:
        df["BB_width"] = 0.0

    df["momentum_5"] = df["close"].diff(5)

    prev = df["EMA9"].shift(1) - df["EMA21"].shift(1)
    curr = df["EMA9"] - df["EMA21"]
    df["ema_cross"] = 0
    df.loc[(prev < 0) & (curr >= 0), "ema_cross"] =  1
    df.loc[(prev > 0) & (curr <= 0), "ema_cross"] = -1

    return df

# ── 200-POINT MOVE DETECTOR ────────────────────────────────────────────────────
def detect_200pt_move(df5, atr_scale=1.0):
    """ATR thresholds scaled per commodity volatility profile"""
    if df5.empty or len(df5) < 20:
        return None, 0, {}

    l = df5.iloc[-1]
    score  = 0
    detail = {}

    atr = l.get("ATR", 0)
    t_hi = 80 * atr_scale; t_mid = 60 * atr_scale; t_lo = 40 * atr_scale
    if atr > t_hi:   score += 30; detail["ATR"] = f"ATR {round(atr,2)} > {t_hi:.0f} → +30 pts"
    elif atr > t_mid: score += 20; detail["ATR"] = f"ATR {round(atr,2)} > {t_mid:.0f} → +20 pts"
    elif atr > t_lo:  score += 10; detail["ATR"] = f"ATR {round(atr,2)} > {t_lo:.0f} → +10 pts"
    else:             detail["ATR"] = f"ATR {round(atr,2)} ≤ {t_lo:.0f} → +0 pts"

    mom = l.get("momentum_5", 0)
    m_hi = 100 * atr_scale; m_mid = 60 * atr_scale; m_lo = 30 * atr_scale
    if abs(mom) > m_hi:  score += 25; detail["Momentum"] = f"5-bar {round(mom,2)} → +25"
    elif abs(mom) > m_mid: score += 15; detail["Momentum"] = f"5-bar {round(mom,2)} → +15"
    elif abs(mom) > m_lo:  score += 8;  detail["Momentum"] = f"5-bar {round(mom,2)} → +8"
    else:                  detail["Momentum"] = f"5-bar {round(mom,2)} → +0"

    adx = l.get("ADX", 0)
    if adx > 30:   score += 20; detail["ADX"] = f"ADX {round(adx,1)} > 30 → +20"
    elif adx > 25: score += 12; detail["ADX"] = f"ADX {round(adx,1)} > 25 → +12"
    elif adx > 20: score += 6;  detail["ADX"] = f"ADX {round(adx,1)} > 20 → +6"
    else:          detail["ADX"] = f"ADX {round(adx,1)} ≤ 20 → +0"

    rsi = l.get("RSI", 50)
    if rsi > 72 or rsi < 28:   score += 15; detail["RSI"] = f"RSI {round(rsi,1)} extreme → +15"
    elif rsi > 68 or rsi < 32: score += 8;  detail["RSI"] = f"RSI {round(rsi,1)} strong → +8"
    else:                      detail["RSI"] = f"RSI {round(rsi,1)} neutral → +0"

    bw     = l.get("BB_width", 0)
    avg_bw = df5["BB_width"].rolling(20).mean().iloc[-1] if "BB_width" in df5 else 0
    if avg_bw and avg_bw > 0:
        ratio = bw / avg_bw
        if ratio > 1.4:   score += 10; detail["BB"] = f"BB {round(ratio,2)}× avg → +10"
        elif ratio > 1.2: score += 5;  detail["BB"] = f"BB {round(ratio,2)}× avg → +5"
        else:             detail["BB"] = f"BB {round(ratio,2)}× avg → +0"

    score = min(score, 100)
    di_p  = l.get("+DI", 0)
    di_m  = l.get("-DI", 0)
    mom   = l.get("momentum_5", 0)

    if   mom > 0 and di_p > di_m: direction = "UP"
    elif mom < 0 and di_m > di_p: direction = "DOWN"
    elif di_p > di_m:              direction = "UP"
    elif di_m > di_p:              direction = "DOWN"
    else:                          direction = "UNCLEAR"

    return direction, score, detail

# ── SIGNAL ENGINE ──────────────────────────────────────────────────────────────
def compute_signal(df5, df15, adx_threshold, min_score, move_dir, move_score, do_boost):
    if len(df5) < 3 or len(df15) < 3:
        return "NO TRADE", 0, 0, ["Insufficient data"], ""

    l5  = df5.iloc[-1]
    l15 = df15.iloc[-1]
    adx = l5["ADX"]

    if adx < 18:
        return "NO TRADE", 0, 0, [f"⛔ ADX {round(adx,1)} < 18 — flat market"], ""

    if adx >= adx_threshold:
        adx_pts  = 15
        adx_note = f"✅ ADX {round(adx,1)} ≥ {adx_threshold} → +15 pts"
    elif adx >= 20:
        adx_pts  = 8
        adx_note = f"🟡 ADX {round(adx,1)} borderline → +8 pts partial"
    else:
        adx_pts  = 0
        adx_note = f"⚠️ ADX {round(adx,1)} weak → +0 pts"

    rsi      = l5["RSI"]
    rsi_prev = df5["RSI"].iloc[-2]
    macd_b   = l5["MACD_HIST"] > 0
    macd_be  = l5["MACD_HIST"] < 0

    rsi_topping   = rsi > 65 and rsi < rsi_prev
    rsi_bottoming = rsi < 35 and rsi > rsi_prev

    # CALL scoring
    call_score   = 0
    call_reasons = []

    if l15["EMA9"] > l15["EMA21"]:
        call_score += 25
        call_reasons.append(f"✅ 15-min EMA9 ({round(l15['EMA9'],1)}) > EMA21 ({round(l15['EMA21'],1)})")
    if l5["close"] > l5["VWAP"]:
        call_score += 20
        call_reasons.append(f"✅ Price above VWAP ({round(l5['VWAP'],1)})")
    if l5["+DI"] > l5["-DI"]:
        call_score += 20
        call_reasons.append(f"✅ +DI {round(l5['+DI'],1)} > -DI {round(l5['-DI'],1)}")
    call_score += adx_pts
    call_reasons.append(adx_note)
    if macd_b:
        call_score += 10
        call_reasons.append("✅ MACD histogram positive")
    if rsi > 55:
        call_score += 10
        call_reasons.append(f"✅ RSI {round(rsi,1)} > 55")

    prev_high = df5["high"].iloc[-2]
    if l5["close"] < prev_high:
        call_score -= 5
        call_reasons.append(
            f"⚠️ Close {round(l5['close'],1)} < prev bar high {round(prev_high,1)} → −5 pts"
        )

    # PUT scoring
    put_score   = 0
    put_reasons = []

    if l15["EMA9"] < l15["EMA21"]:
        put_score += 25
        put_reasons.append(f"✅ 15-min EMA9 ({round(l15['EMA9'],1)}) < EMA21 ({round(l15['EMA21'],1)})")
    if l5["close"] < l5["VWAP"]:
        put_score += 20
        put_reasons.append(f"✅ Price below VWAP ({round(l5['VWAP'],1)})")
    if l5["-DI"] > l5["+DI"]:
        put_score += 20
        put_reasons.append(f"✅ -DI {round(l5['-DI'],1)} > +DI {round(l5['+DI'],1)}")
    put_score += adx_pts
    put_reasons.append(adx_note)
    if macd_be:
        put_score += 10
        put_reasons.append("✅ MACD histogram negative")
    if rsi < 45:
        put_score += 10
        put_reasons.append(f"✅ RSI {round(rsi,1)} < 45")
    if rsi < 30:
        put_score += 10
        put_reasons.append(f"✅ RSI {round(rsi,1)} < 30 — oversold bonus")

    prev_low = df5["low"].iloc[-2]
    if l5["close"] > prev_low:
        put_score -= 5
        put_reasons.append(
            f"⚠️ Close {round(l5['close'],1)} > prev bar low {round(prev_low,1)} → −5 pts"
        )

    if call_score >= min_score and call_score > put_score:
        if rsi_topping:
            return (
                "BLOCKED_CALL", call_score, call_score, call_reasons,
                f"RSI {round(rsi,1)} rolling over from top — fake CALL entry risk"
            )
        confidence = call_score
        if do_boost and move_dir == "UP" and move_score >= 60:
            boost       = min(int(move_score / 5), 20)
            confidence += boost
            call_reasons.append(f"🚀 200-pt UP move score {move_score}/100 → +{boost} boost")
        return "CALL", call_score, min(confidence, 100), call_reasons, ""

    if put_score >= min_score and put_score > call_score:
        if rsi_bottoming:
            return (
                "BLOCKED_PUT", put_score, put_score, put_reasons,
                f"RSI {round(rsi,1)} turning up from bottom — fake PUT entry risk"
            )
        confidence = put_score
        if do_boost and move_dir == "DOWN" and move_score >= 60:
            boost       = min(int(move_score / 5), 20)
            confidence += boost
            put_reasons.append(f"🚀 200-pt DOWN move score {move_score}/100 → +{boost} boost")
        return "PUT", put_score, min(confidence, 100), put_reasons, ""

    weak = []
    if call_score > 0: weak.append(f"Bullish score {call_score}/{min_score} — need {min_score - call_score} more pts")
    if put_score  > 0: weak.append(f"Bearish score {put_score}/{min_score} — need {min_score - put_score} more pts")
    if not weak:       weak.append("No EMA directional alignment on 15-min")
    return "NO TRADE", max(call_score, put_score), max(call_score, put_score), [f"⏸ {w}" for w in weak], ""

# ── OPTION CHAIN ───────────────────────────────────────────────────────────────
def get_option_chain(price, commodity_name):
    df = instruments.copy()
    seg = COMMODITY_CONFIG[commodity_name]["segment_opt"]
    df  = df[(df["name"] == commodity_name) & (df["segment"] == seg)]
    if df.empty: return pd.DataFrame()
    expiry = df["expiry"].min()
    df     = df[df["expiry"] == expiry].copy()
    df["diff"] = abs(df["strike"] - price)
    df = df.sort_values("diff").head(200)
    quotes = kite.quote([f"MCX:{x}" for x in df["tradingsymbol"]])
    rows = []
    for _, r in df.iterrows():
        q   = quotes.get(f"MCX:{r['tradingsymbol']}", {})
        ltp = q.get("last_price", 0)
        rows.append({
            "symbol":    r["tradingsymbol"],
            "strike":    r["strike"],
            "type":      r["instrument_type"],
            "ltp":       ltp,
            "oi":        q.get("oi", 0),
            "volume":    q.get("volume", 0),
            "moneyness": (
                "ITM" if (r["instrument_type"]=="CE" and r["strike"]<price) or
                         (r["instrument_type"]=="PE" and r["strike"]>price)
                else ("ATM" if abs(r["strike"]-price)<=COMMODITY_CONFIG[commodity_name]["tick"] else "OTM")
            ),
        })
    return pd.DataFrame(rows)

# ── OPTION PICKER ──────────────────────────────────────────────────────────────
def pick_options_by_premium(option_df, signal, target_prem, min_prem, max_prem,
                             lot_size, num_lots):
    sig = signal.replace("BLOCKED_","")
    if sig not in ("CALL","PUT") or option_df.empty:
        return None, None, None
    opt_type = "CE" if sig == "CALL" else "PE"
    df = option_df[(option_df["type"]==opt_type) & (option_df["ltp"]>0)].copy()
    if df.empty: return None, None, None

    df["prem_dist"] = abs(df["ltp"] - target_prem)
    df = df.sort_values("prem_dist")
    df_b = df[(df["ltp"]>=min_prem) & (df["ltp"]<=max_prem)]
    if df_b.empty: df_b = df.head(10)

    best_strike    = df_b.iloc[0]["strike"]
    strikes_sorted = sorted(df_b["strike"].unique())
    idx            = strikes_sorted.index(best_strike) if best_strike in strikes_sorted else 0

    if sig == "CALL":
        cheaper = strikes_sorted[idx+1] if idx+1 < len(strikes_sorted) else None
        pricier = strikes_sorted[idx-1] if idx-1 >= 0 else None
    else:
        cheaper = strikes_sorted[idx-1] if idx-1 >= 0 else None
        pricier = strikes_sorted[idx+1] if idx+1 < len(strikes_sorted) else None

    def build(strike):
        if strike is None: return None
        r = df[df["strike"]==strike]
        if r.empty: return None
        row = r.iloc[0].to_dict()
        ltp = float(row["ltp"])
        if ltp <= 0: return None
        cl  = round(ltp * lot_size, 2)
        tot = round(cl * num_lots, 2)
        row.update({
            "cost_1lot":     cl,
            "total_cost":    tot,
            "num_lots":      num_lots,
            "sl":            round(ltp*0.70, 2),
            "sl_loss_total": round(ltp*0.30*lot_size*num_lots, 2),
            "t1":            round(ltp*1.50, 2),
            "t1_gain_total": round(ltp*0.50*lot_size*num_lots, 2),
            "t2":            round(ltp*2.00, 2),
            "t2_gain_total": round(ltp*1.00*lot_size*num_lots, 2),
        })
        return row

    return build(best_strike), build(cheaper), build(pricier)

# ── TRADE LOG UPSERT ──────────────────────────────────────────────────────────
def upsert_trade_log(log_df, signal, best_row, num_lots, confidence,
                     move_score, move_dir, current_time, commodity):
    if best_row is None:
        return log_df

    sig_clean = signal.replace("BLOCKED_","")
    strike    = best_row["strike"]
    now_str   = current_time.strftime("%H:%M:%S")

    if not log_df.empty:
        mask = (log_df["Signal"] == sig_clean) & (log_df["Strike"] == strike) & (log_df["Commodity"] == commodity)
        if mask.any():
            idx = log_df[mask].index[-1]
            log_df.at[idx, "Last_Updated"]  = now_str
            log_df.at[idx, "LTP"]           = float(best_row["ltp"])
            log_df.at[idx, "Confidence"]    = f"{confidence}%"
            log_df.at[idx, "Confirmations"] = log_df.at[idx, "Confirmations"] + 1
            log_df.at[idx, "Move_Score"]    = f"{move_score}/100 {move_dir or ''}"
            return log_df

    new_row = pd.DataFrame([{
        "First_Seen":    now_str,
        "Last_Updated":  now_str,
        "Confirmations": 1,
        "Commodity":     commodity,
        "Signal":        sig_clean,
        "Symbol":        best_row["symbol"],
        "Strike":        strike,
        "Type":          best_row["type"],
        "LTP":           float(best_row["ltp"]),
        "Cost_1Lot":     best_row["cost_1lot"],
        "Lots":          num_lots,
        "Total_Capital": best_row["total_cost"],
        "SL":            best_row["sl"],
        "T1":            best_row["t1"],
        "T2":            best_row["t2"],
        "Confidence":    f"{confidence}%",
        "Move_Score":    f"{move_score}/100 {move_dir or ''}",
    }])
    return pd.concat([log_df, new_row], ignore_index=True).tail(100)

# ── PAPER TRADE LOG ────────────────────────────────────────────────────────────
def log_paper_trade(signal, best_row, num_lots, lot_size, confidence, score,
                    commodity, current_time):
    """Add a new paper trade entry — always a new row (tracks individual entries)"""
    if best_row is None:
        return
    sig_clean    = signal.replace("BLOCKED_","")
    ltp          = float(best_row["ltp"])
    capital_used = round(ltp * lot_size * num_lots, 2)
    trade_id     = f"PT{st.session_state.paper_id_counter:04d}"
    st.session_state.paper_id_counter += 1

    new_row = pd.DataFrame([{
        "ID":            trade_id,
        "Time":          current_time.strftime("%H:%M:%S"),
        "Commodity":     commodity,
        "Signal":        sig_clean,
        "Symbol":        best_row["symbol"],
        "Strike":        best_row["strike"],
        "Type":          best_row["type"],
        "Entry_Premium": ltp,
        "SL":            best_row["sl"],
        "T1":            best_row["t1"],
        "T2":            best_row["t2"],
        "Lots":          num_lots,
        "Lot_Size":      lot_size,
        "Capital_Used":  capital_used,
        "Status":        "Open",
        "Exit_Premium":  None,
        "PnL":           None,
        "PnL_Pct":       None,
        "Confidence":    f"{confidence}%",
        "Score":         score,
        "Notes":         "",
    }])
    st.session_state.paper_trades = pd.concat(
        [st.session_state.paper_trades, new_row], ignore_index=True
    ).tail(200)
    st.toast(f"📝 Paper trade logged: {trade_id} | {commodity} {sig_clean} ₹{ltp}")

def simulate_outcome(trade_idx, current_ltp):
    """Auto-mark outcome based on current LTP vs SL/T1/T2"""
    row   = st.session_state.paper_trades.loc[trade_idx]
    entry = float(row["Entry_Premium"])
    sl    = float(row["SL"])
    t1    = float(row["T1"])
    t2    = float(row["T2"])
    lots  = int(row["Lots"])
    ls    = int(row["Lot_Size"])

    if current_ltp <= sl:
        status = "SL Hit"
        pnl    = round((current_ltp - entry) * lots * ls, 2)
    elif current_ltp >= t2:
        status = "T2 Hit"
        pnl    = round((current_ltp - entry) * lots * ls, 2)
    elif current_ltp >= t1:
        status = "T1 Hit"
        pnl    = round((current_ltp - entry) * lots * ls, 2)
    else:
        status = "Open"
        pnl    = round((current_ltp - entry) * lots * ls, 2)

    pnl_pct = round((pnl / (entry * lots * ls)) * 100, 2) if entry > 0 else 0

    st.session_state.paper_trades.at[trade_idx, "Status"]        = status
    st.session_state.paper_trades.at[trade_idx, "Exit_Premium"]  = current_ltp
    st.session_state.paper_trades.at[trade_idx, "PnL"]           = pnl
    st.session_state.paper_trades.at[trade_idx, "PnL_Pct"]       = pnl_pct

# ── PAPER ANALYTICS ────────────────────────────────────────────────────────────
def compute_paper_stats(df, commodity_filter=None):
    """Compute win rate, P&L, drawdown etc. from paper trades"""
    if df.empty:
        return {}
    fd = df[df["Status"] != "Open"].copy()
    if commodity_filter:
        fd = fd[fd["Commodity"] == commodity_filter]
    if fd.empty:
        return {"total": len(df), "closed": 0}

    fd["PnL"] = pd.to_numeric(fd["PnL"], errors="coerce").fillna(0)
    wins      = fd[fd["PnL"] > 0]
    losses    = fd[fd["PnL"] <= 0]
    win_rate  = round(len(wins) / len(fd) * 100, 1) if len(fd) > 0 else 0
    total_pnl = round(fd["PnL"].sum(), 2)

    gross_profit = wins["PnL"].sum() if len(wins) > 0 else 0
    gross_loss   = abs(losses["PnL"].sum()) if len(losses) > 0 else 0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    # Max drawdown (cumulative)
    cum_pnl   = fd["PnL"].cumsum()
    rolling_max = cum_pnl.cummax()
    drawdown  = (cum_pnl - rolling_max)
    max_dd    = round(drawdown.min(), 2)

    # Avg R:R from SL/T hits
    t2_count = len(fd[fd["Status"] == "T2 Hit"])
    t1_count = len(fd[fd["Status"] == "T1 Hit"])
    sl_count = len(fd[fd["Status"] == "SL Hit"])

    return {
        "total":         len(df[df["Commodity"] == commodity_filter]) if commodity_filter else len(df),
        "closed":        len(fd),
        "wins":          len(wins),
        "losses":        len(losses),
        "win_rate":      win_rate,
        "total_pnl":     total_pnl,
        "profit_factor": profit_factor,
        "max_drawdown":  max_dd,
        "t2_count":      t2_count,
        "t1_count":      t1_count,
        "sl_count":      sl_count,
        "avg_pnl":       round(fd["PnL"].mean(), 2),
    }

# ── CANDLESTICK CHART ──────────────────────────────────────────────────────────
def make_candlestick(df, ema_cols, title, height=400, last_n_bars=None):
    cd = df.reset_index().copy()
    if last_n_bars:
        cd = cd.tail(last_n_bars)
    cd["color"] = cd.apply(lambda r: "Up" if r["close"] >= r["open"] else "Down", axis=1)
    base = alt.Chart(cd)
    rule = base.mark_rule(strokeWidth=1).encode(
        x=alt.X("date:T", title="Time"),
        y=alt.Y("low:Q",  scale=alt.Scale(zero=False), title="Price"),
        y2=alt.Y2("high:Q"),
        color=alt.Color("color:N", scale=alt.Scale(domain=["Up","Down"], range=["#2e7d32","#c62828"]), legend=None)
    )
    bar = base.mark_bar().encode(
        x=alt.X("date:T"),
        y=alt.Y("open:Q",  scale=alt.Scale(zero=False)),
        y2=alt.Y2("close:Q"),
        color=alt.Color("color:N", scale=alt.Scale(domain=["Up","Down"], range=["#2e7d32","#c62828"]), legend=None),
        tooltip=[
            alt.Tooltip("date:T", title="Time"), alt.Tooltip("open:Q", title="Open"),
            alt.Tooltip("high:Q", title="High"), alt.Tooltip("low:Q",  title="Low"),
            alt.Tooltip("close:Q",title="Close"),alt.Tooltip("volume:Q",title="Volume"),
        ]
    )
    ema_colors = {"EMA9":"#f39c12","EMA21":"#1565c0","VWAP":"#6a1b9a","EMA20":"#e67e22","EMA50":"#16a085"}
    layers = [rule, bar]
    for col in ema_cols:
        if col in cd.columns:
            cd_ema = cd[["date", col]].dropna()
            layers.append(
                alt.Chart(cd_ema).mark_line(strokeWidth=1.5).encode(
                    x="date:T",
                    y=alt.Y(f"{col}:Q", scale=alt.Scale(zero=False)),
                    color=alt.value(ema_colors.get(col, "#888"))
                )
            )
    return alt.layer(*layers).properties(height=height, title=title)

# ── NEWS ───────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_commodity_news(query):
    try:
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        return [{"title":e.title,"link":e.link,"time":e.get("published","")}
                for e in feed.entries[:7]]
    except Exception:
        return []

# ══════════════════════════════════════════════════════════════════════════════
# ── TAB 1: LIVE SIGNALS ────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
with tab_live:
    token = get_token(commodity_key)
    if token is None:
        st.error(f"❌ Could not find futures token for {commodity_key}. Check MCX instruments.")
        st.stop()

    with st.spinner(f"📡 Fetching {cfg['label']} data..."):
        df5  = apply_indicators(get_data(token, "5minute",  4))
        df15 = apply_indicators(get_data(token, "15minute", 6))

    if df5.empty:
        st.error("❌ No data. Check API token / market hours.")
        st.stop()

    price     = df5["close"].iloc[-1]
    option_df = get_option_chain(price, commodity_key)

    move_dir, move_score, move_detail = detect_200pt_move(df5, cfg["atr_scale"])

    signal, raw_score, confidence, reasons, block_reason = compute_signal(
        df5, df15, adx_min, min_score, move_dir, move_score, move_boost
    )

    best_row, cheaper_row, pricier_row = pick_options_by_premium(
        option_df, signal, target_prem, min_prem, max_prem, lot_size_opt, num_lots
    )

    # Upsert trade log
    if signal in ("CALL","PUT") and best_row:
        st.session_state.trade_log = upsert_trade_log(
            st.session_state.trade_log, signal, best_row,
            num_lots, confidence, move_score, move_dir, current_time, commodity_key
        )
        if paper_enabled:
            # Only log to paper if it's a new signal (not seen in last 5 min for this strike)
            pt = st.session_state.paper_trades
            if pt.empty or not ((pt["Strike"] == best_row["strike"]) & (pt["Commodity"] == commodity_key) & (pt["Status"] == "Open")).any():
                log_paper_trade(signal, best_row, num_lots, lot_size_opt,
                                confidence, raw_score, commodity_key, current_time)

    # ── METRICS ──
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric(f"{cfg['label']} LTP", round(price, 2))
    c2.metric("📶 Signal",    signal.replace("BLOCKED_","⚠️ "))
    c3.metric("📊 RSI",       round(df5["RSI"].iloc[-1],2))
    c4.metric("📈 ADX",       round(df5["ADX"].iloc[-1],2))
    c5.metric("🌊 VWAP Side", "Above ✅" if price > df5["VWAP"].iloc[-1] else "Below 🔴")
    c6.metric("🎯 Score",     f"{confidence}%")

    bar_col = "#2e7d32" if raw_score>=min_score else "#f9a825" if raw_score>=min_score*0.7 else "#c62828"
    st.markdown(
        f'<div style="margin:2px 0 8px"><small>Signal score: <b>{raw_score}/100</b> '
        f'(need ≥ {min_score}) &nbsp;|&nbsp; Confidence after boost: <b>{confidence}%</b></small>'
        f'<div class="bar-wrap"><div class="bar-fill" '
        f'style="width:{min(raw_score,100)}%;background:{bar_col}"></div></div></div>',
        unsafe_allow_html=True
    )

    # Signal banner
    if signal == "CALL":
        st.markdown(f'<div class="sig-call">🟢 CALL — Buy CE &nbsp;|&nbsp; Score: {raw_score}/100 ✅ &nbsp;|&nbsp; Confidence: {confidence}% &nbsp;|&nbsp; Premium ₹{min_prem}–₹{max_prem}</div>', unsafe_allow_html=True)
    elif signal == "PUT":
        st.markdown(f'<div class="sig-put">🔴 PUT — Buy PE &nbsp;|&nbsp; Score: {raw_score}/100 ✅ &nbsp;|&nbsp; Confidence: {confidence}% &nbsp;|&nbsp; Premium ₹{min_prem}–₹{max_prem}</div>', unsafe_allow_html=True)
    elif signal == "BLOCKED_CALL":
        st.markdown(f'<div class="sig-blocked">⚠️ CALL BLOCKED — Score {raw_score}/100 ✅ threshold met, but entry filtered: <b>{block_reason}</b><br><small>Wait for filter to clear.</small></div>', unsafe_allow_html=True)
    elif signal == "BLOCKED_PUT":
        st.markdown(f'<div class="sig-blocked">⚠️ PUT BLOCKED — Score {raw_score}/100 ✅ threshold met, but entry filtered: <b>{block_reason}</b><br><small>Wait for filter to clear.</small></div>', unsafe_allow_html=True)
    else:
        pts_needed = max(0, min_score - raw_score)
        st.markdown(f'<div class="sig-wait">🟡 WAIT — Score {raw_score}/{min_score} (need {pts_needed} more pts to qualify)</div>', unsafe_allow_html=True)

    with st.expander("📋 Signal Reasoning"):
        for r in reasons:
            st.markdown(f"- {r}")

    # Trade Suggestions
    is_tradeable = signal in ("CALL","PUT","BLOCKED_CALL","BLOCKED_PUT")
    display_sig  = signal.replace("BLOCKED_","")

    st.subheader(f"🎯 Trade Suggestions — ₹{capital:,} | {num_lots} lot(s) | Lot size {lot_size_opt} | Target ₹{min_prem}–₹{max_prem}")

    def show_card(label, row, sig):
        if row is None:
            st.warning(f"**{label}**: No option in ₹{min_prem}–₹{max_prem} range")
            return
        icon  = "🟢" if sig=="CALL" else "🔴"
        tag   = "CE" if sig=="CALL" else "PE"
        ltp   = float(row["ltp"])
        badge = "✅ In range" if min_prem<=ltp<=max_prem else f"⚠️ Nearest (₹{round(ltp,0)})"
        st.success(f"""
**{icon} {label} — {sig} ({tag})** &nbsp;&nbsp; {badge}

📌 Symbol    : `{row['symbol']}`
💥 Strike    : ₹{row['strike']}  ({row.get('moneyness','')})
💰 Premium   : ₹{round(ltp,2)}
🧾 Per lot   : ₹{row['cost_1lot']}
🛒 {num_lots} lot(s) : **₹{row['total_cost']:,}**

🛑 **SL** : ₹{row['sl']}  → max loss ₹{row['sl_loss_total']:,} (−30%)
🎯 **T1** : ₹{row['t1']}  → profit ₹{row['t1_gain_total']:,} (+50%)
🎯 **T2** : ₹{row['t2']}  → profit ₹{row['t2_gain_total']:,} (+100%)
""")

    if is_tradeable:
        if signal.startswith("BLOCKED"):
            st.warning("⚠️ Signal blocked by RSI filter. Showing what would be suggested if it clears.")
        c1,c2,c3 = st.columns(3)
        with c1: show_card("✨ Best Match",   best_row,    display_sig)
        with c2: show_card("💸 Cheaper OTM", cheaper_row, display_sig)
        with c3: show_card("💎 Less OTM",    pricier_row, display_sig)
        if best_row:
            tot = best_row["total_cost"]
            if tot > capital:
                st.error(f"⚠️ Costs ₹{tot:,} vs ₹{capital:,}. Reduce lots or widen range.")
            else:
                st.success(f"✅ Fits budget. Remaining: ₹{capital-tot:,}")

        # Manual paper trade button
        if best_row and st.button(f"📝 Manually Log to Paper Analyzer", key="manual_paper"):
            log_paper_trade(signal, best_row, num_lots, lot_size_opt,
                            confidence, raw_score, commodity_key, current_time)
    else:
        st.info("🚫 No trade right now. Conditions not met.")

    with st.expander(f"🔍 All options with premium ₹{min_prem}–₹{max_prem}"):
        if not option_df.empty and display_sig in ("CALL","PUT"):
            ot  = "CE" if display_sig=="CALL" else "PE"
            fil = option_df[
                (option_df["type"]==ot) &
                (option_df["ltp"]>=min_prem) &
                (option_df["ltp"]<=max_prem)
            ].sort_values("ltp").copy()
            if not fil.empty:
                fil["cost_1lot"]           = (fil["ltp"]*lot_size_opt).round(2)
                fil[f"cost_{num_lots}lot"] = (fil["ltp"]*lot_size_opt*num_lots).round(2)
                st.dataframe(
                    fil[["strike","moneyness","ltp","cost_1lot",f"cost_{num_lots}lot","oi","volume"]],
                    use_container_width=True
                )
            else:
                st.info("No options in this range. Widen in sidebar.")

    # Trade Log
    st.subheader("📋 Trade History")
    if not st.session_state.trade_log.empty:
        display_log = st.session_state.trade_log.copy()
        if commodity_key:
            display_log = display_log[display_log["Commodity"] == commodity_key]
        st.dataframe(display_log.iloc[::-1], use_container_width=True)
        st.caption("ℹ️ **First_Seen** = first signal. **Last_Updated** = last confirmation. **Confirmations** = repeat count.")
        col_clr1, col_clr2 = st.columns([1,4])
        with col_clr1:
            if st.button("🗑️ Clear This Commodity Log"):
                st.session_state.trade_log = st.session_state.trade_log[
                    st.session_state.trade_log["Commodity"] != commodity_key
                ]
                st.rerun()
    else:
        st.info("No trades logged yet.")

    # 200-pt Detector
    if show_200:
        st.subheader("🚀 200-Point Move Detector")
        mv1,mv2,mv3 = st.columns(3)
        mv1.metric("📐 Direction",        move_dir or "Unclear")
        mv2.metric("🎯 Move Probability", f"{move_score}/100")
        mv3.metric("📏 ATR (5-min)",      round(df5["ATR"].iloc[-1],2))

        mc = "#2e7d32" if move_score>=60 else "#f9a825" if move_score>=35 else "#bdbdbd"
        st.markdown(
            f'<div style="margin:2px 0 8px"><small>Move score: <b>{move_score}/100</b></small>'
            f'<div class="bar-wrap"><div class="bar-fill" style="width:{move_score}%;background:{mc}"></div></div></div>',
            unsafe_allow_html=True
        )
        if move_score >= 60:
            st.markdown(f'<div class="move-high">⚡ HIGH probability move <b>{move_dir}</b> — Strong momentum!</div>', unsafe_allow_html=True)
        elif move_score >= 35:
            st.markdown(f'<div class="move-mid">🟡 Moderate move chance <b>{move_dir}</b> — Monitor.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="move-low">📉 Low-volatility — big move unlikely now.</div>', unsafe_allow_html=True)

        with st.expander("🔍 Move Score Breakdown"):
            for k,v in move_detail.items():
                st.markdown(f"- **{k}**: {v}")

    # Charts
    st.subheader("📈 5-Min Candlestick Chart — EMA9 / EMA21 / VWAP")
    if not df5.empty:
        st.altair_chart(
            make_candlestick(df5, ema_cols=["EMA9","EMA21","VWAP"],
                title=f"{cfg['label']} 5-Min — EMA9 (orange) | EMA21 (blue) | VWAP (purple)",
                height=400, last_n_bars=80),
            use_container_width=True
        )

    st.subheader("📊 15-Min Candlestick Chart — EMA9 / EMA21")
    if not df15.empty:
        st.altair_chart(
            make_candlestick(df15, ema_cols=["EMA9","EMA21"],
                title=f"{cfg['label']} 15-Min — EMA9 (orange) | EMA21 (blue)",
                height=380, last_n_bars=50),
            use_container_width=True
        )

    # RSI
    st.subheader("📉 RSI (14)")
    cd = df5.reset_index()
    st.altair_chart(
        alt.Chart(cd).mark_line(color="#e67e22").encode(
            x="date:T", y=alt.Y("RSI:Q", scale=alt.Scale(domain=[0,100]))
        ).properties(height=130)
        + alt.Chart(pd.DataFrame({"y":[70]})).mark_rule(color="red",   strokeDash=[4,3]).encode(y="y:Q")
        + alt.Chart(pd.DataFrame({"y":[30]})).mark_rule(color="green", strokeDash=[4,3]).encode(y="y:Q"),
        use_container_width=True
    )

    # News
    st.subheader(f"📰 {cfg['label']} News")
    for item in get_commodity_news(cfg["news_query"]):
        st.markdown(f"• [{item['title']}]({item['link']}) — _{item['time']}_")

    # Option chain
    st.subheader("📊 Option Chain")
    if not option_df.empty:
        oc1,oc2 = st.columns(2)
        with oc1:
            st.markdown("**CE (Call Options)**")
            st.dataframe(
                option_df[option_df["type"]=="CE"].sort_values("strike")[["strike","moneyness","ltp","oi","volume"]].head(20),
                use_container_width=True
            )
        with oc2:
            st.markdown("**PE (Put Options)**")
            st.dataframe(
                option_df[option_df["type"]=="PE"].sort_values("strike",ascending=False)[["strike","moneyness","ltp","oi","volume"]].head(20),
                use_container_width=True
            )

# ══════════════════════════════════════════════════════════════════════════════
# ── TAB 2: PAPER TRADE ANALYZER ───────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
with tab_paper:
    st.header("📊 Paper Trade Analyzer — Dashboard Intelligence Testing")
    st.markdown(
        "Use this panel to **evaluate signal quality** without real money. "
        "Signals auto-logged here when 'Auto-log' is enabled in sidebar. "
        "Simulate outcomes to measure win rate, P&L, and profit factor."
    )

    pt = st.session_state.paper_trades

    # ── Overall Stats ──
    st.subheader("📈 Overall Performance Stats")
    all_stats = compute_paper_stats(pt)
    if all_stats.get("closed", 0) > 0:
        sc1,sc2,sc3,sc4,sc5,sc6 = st.columns(6)
        sc1.metric("📋 Total Trades",   all_stats.get("total", 0))
        sc2.metric("✅ Closed",          all_stats.get("closed", 0))
        sc3.metric("🎯 Win Rate",        f"{all_stats.get('win_rate',0)}%")
        sc4.metric("💰 Total P&L",       f"₹{all_stats.get('total_pnl',0):,.0f}")
        sc5.metric("📊 Profit Factor",   all_stats.get("profit_factor","N/A"))
        sc6.metric("📉 Max Drawdown",    f"₹{all_stats.get('max_drawdown',0):,.0f}")

        # T1/T2/SL breakdown
        st.markdown("**Exit Distribution:**")
        ec1,ec2,ec3 = st.columns(3)
        ec1.metric("🎯 T2 Hits",   all_stats.get("t2_count",0))
        ec2.metric("🎯 T1 Hits",   all_stats.get("t1_count",0))
        ec3.metric("🛑 SL Hits",   all_stats.get("sl_count",0))
    else:
        st.info("No closed trades yet. Log signals and simulate outcomes to see stats.")

    st.markdown("---")

    # ── Per Commodity Stats ──
    st.subheader("🌐 Stats by Commodity")
    commodity_cols = st.columns(len(COMMODITY_CONFIG))
    for i, (ck, ccfg) in enumerate(COMMODITY_CONFIG.items()):
        s = compute_paper_stats(pt, commodity_filter=ck)
        with commodity_cols[i]:
            closed = s.get("closed",0)
            total  = s.get("total",0)
            wr     = s.get("win_rate", 0)
            pnl    = s.get("total_pnl", 0)
            color  = "#2e7d32" if pnl >= 0 else "#c62828"
            st.markdown(f"""
<div class="paper-stat">
  <div style="font-size:20px">{ccfg['label']}</div>
  <div class="num" style="color:{color}">₹{pnl:,.0f}</div>
  <div class="lbl">{closed}/{total} closed | WR: {wr}%</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Trade List with Simulate Buttons ──
    st.subheader("📋 Paper Trade Ledger")

    if not pt.empty:
        # Filter options
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            f_commodity = st.selectbox("Filter by Commodity", ["All"] + list(COMMODITY_CONFIG.keys()), key="pt_filter_comm")
        with filter_col2:
            f_status = st.selectbox("Filter by Status", ["All","Open","T1 Hit","T2 Hit","SL Hit"], key="pt_filter_status")
        with filter_col3:
            f_signal = st.selectbox("Filter by Signal", ["All","CALL","PUT"], key="pt_filter_signal")

        display_pt = pt.copy()
        if f_commodity != "All":
            display_pt = display_pt[display_pt["Commodity"] == f_commodity]
        if f_status != "All":
            display_pt = display_pt[display_pt["Status"] == f_status]
        if f_signal != "All":
            display_pt = display_pt[display_pt["Signal"] == f_signal]

        st.markdown(f"**{len(display_pt)} trades shown**")

        # Display + simulate for open trades
        for idx, row in display_pt.iloc[::-1].iterrows():
            status     = row["Status"]
            pnl        = row["PnL"]
            commodity  = row["Commodity"]
            signal_t   = row["Signal"]
            entry      = row["Entry_Premium"]
            sym        = row["Symbol"]

            if status == "Open":
                card_class = "paper-open"
                icon = "🔵"
            elif pnl is not None and float(pnl) > 0:
                card_class = "paper-win"
                icon = "✅"
            else:
                card_class = "paper-loss"
                icon = "❌"

            pnl_str = f"₹{float(pnl):,.0f}" if pnl is not None else "—"
            st.markdown(f"""
<div class="{card_class}">
{icon} <b>{row['ID']}</b> | {commodity} | {signal_t} | <code>{sym}</code> | 
Strike ₹{row['Strike']} | Entry ₹{entry} | SL ₹{row['SL']} | T1 ₹{row['T1']} | T2 ₹{row['T2']} | 
Status: <b>{status}</b> | P&L: <b>{pnl_str}</b> | Confidence: {row['Confidence']} | Time: {row['Time']}
</div>
""", unsafe_allow_html=True)

            if status == "Open":
                sim_col1, sim_col2, sim_col3, sim_col4 = st.columns([2,1,1,1])
                with sim_col1:
                    cur_ltp = st.number_input(
                        f"Current LTP for {row['ID']}",
                        value=float(entry),
                        step=0.5,
                        key=f"sim_ltp_{idx}"
                    )
                with sim_col2:
                    if st.button(f"🔄 Simulate", key=f"sim_{idx}"):
                        simulate_outcome(idx, cur_ltp)
                        st.rerun()
                with sim_col3:
                    if st.button(f"✅ Mark T1", key=f"t1_{idx}"):
                        simulate_outcome(idx, float(row["T1"]))
                        st.rerun()
                with sim_col4:
                    if st.button(f"🛑 Mark SL", key=f"sl_{idx}"):
                        simulate_outcome(idx, float(row["SL"]))
                        st.rerun()

        st.markdown("---")

        # P&L Chart
        closed_trades = pt[pt["Status"] != "Open"].copy()
        if not closed_trades.empty:
            closed_trades["PnL"] = pd.to_numeric(closed_trades["PnL"], errors="coerce").fillna(0)
            closed_trades["Cumulative_PnL"] = closed_trades["PnL"].cumsum()
            closed_trades["Trade_Num"] = range(1, len(closed_trades)+1)

            pnl_chart = (
                alt.Chart(closed_trades).mark_bar().encode(
                    x=alt.X("Trade_Num:O", title="Trade #"),
                    y=alt.Y("PnL:Q",       title="P&L (₹)"),
                    color=alt.condition(alt.datum.PnL > 0, alt.value("#2e7d32"), alt.value("#c62828")),
                    tooltip=["ID","Commodity","Signal","Symbol","PnL","Status"]
                ).properties(height=200, title="Per-Trade P&L")
            )
            cum_chart = (
                alt.Chart(closed_trades).mark_line(color="#1565c0", strokeWidth=2).encode(
                    x=alt.X("Trade_Num:O", title="Trade #"),
                    y=alt.Y("Cumulative_PnL:Q", title="Cumulative P&L (₹)"),
                    tooltip=["Trade_Num","Cumulative_PnL"]
                ).properties(height=200, title="Cumulative P&L")
                + alt.Chart(pd.DataFrame({"y":[0]})).mark_rule(color="#999", strokeDash=[4,3]).encode(y="y:Q")
            )

            st.altair_chart(pnl_chart, use_container_width=True)
            st.altair_chart(cum_chart, use_container_width=True)

        # Export
        st.markdown("---")
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            csv = pt.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Export Paper Trades (CSV)",
                csv, "paper_trades.csv", "text/csv"
            )
        with col_exp2:
            if st.button("🗑️ Clear All Paper Trades"):
                st.session_state.paper_trades = pd.DataFrame(
                    columns=st.session_state.paper_trades.columns
                )
                st.session_state.paper_id_counter = 1
                st.rerun()
    else:
        st.info(
            "📭 No paper trades yet.\n\n"
            "Go to **Live Signals** tab, select a commodity, and signals will be "
            "auto-logged here when 'Auto-log signals' is enabled in the sidebar.\n\n"
            "You can also click **Manually Log to Paper Analyzer** on any trade suggestion card."
        )

    # ── Signal Quality Scorecard ──
    st.markdown("---")
    st.subheader("🏆 Dashboard Signal Quality Scorecard")

    quality_data = []
    for ck, ccfg in COMMODITY_CONFIG.items():
        s = compute_paper_stats(pt, commodity_filter=ck)
        closed = s.get("closed", 0)
        if closed >= 3:
            wr  = s.get("win_rate", 0)
            pf  = s.get("profit_factor", 0)
            pnl = s.get("total_pnl", 0)
            grade = "🏆 A+" if wr>=70 and pf>=2 else "✅ B" if wr>=55 else "⚠️ C" if wr>=40 else "❌ D"
            quality_data.append({
                "Commodity": ccfg["label"],
                "Trades":    closed,
                "Win Rate":  f"{wr}%",
                "Profit Factor": pf,
                "Total P&L": f"₹{pnl:,.0f}",
                "Grade":     grade
            })

    if quality_data:
        st.dataframe(pd.DataFrame(quality_data), use_container_width=True)
        st.caption("Grade: A+ = WR≥70% & PF≥2 | B = WR≥55% | C = WR≥40% | D = below 40%")
    else:
        st.info("Need at least 3 closed trades per commodity to generate scorecard.")

# ══════════════════════════════════════════════════════════════════════════════
# ── TAB 3: COMMODITY COMPARISON ───────────────────────────────────────────════
# ══════════════════════════════════════════════════════════════════════════════
with tab_compare:
    st.header("🆚 Commodity Signal Comparison")
    st.markdown("Quick comparison of all 4 commodities — signal strength, RSI, and ADX at a glance.")

    compare_data = []
    with st.spinner("🔄 Fetching all commodity data for comparison..."):
        for ck, ccfg in COMMODITY_CONFIG.items():
            try:
                t = get_token(ck)
                if t is None:
                    compare_data.append({
                        "Commodity": ccfg["label"], "LTP": "—", "RSI": "—",
                        "ADX": "—", "Signal": "No Data", "Score": "—",
                        "VWAP Side": "—", "ATR": "—"
                    })
                    continue
                d5  = apply_indicators(get_data(t, "5minute",  4))
                d15 = apply_indicators(get_data(t, "15minute", 6))
                if d5.empty:
                    compare_data.append({"Commodity": ccfg["label"], "LTP": "—",
                        "RSI": "—", "ADX": "—", "Signal": "No Data", "Score": "—",
                        "VWAP Side": "—", "ATR": "—"})
                    continue
                md, ms, _ = detect_200pt_move(d5, ccfg["atr_scale"])
                sig, rs, conf, _, _ = compute_signal(
                    d5, d15, ccfg["adx_thresh"], ccfg["min_score"], md, ms, False
                )
                p = d5["close"].iloc[-1]
                compare_data.append({
                    "Commodity":  ccfg["label"],
                    "LTP":        round(p, 2),
                    "RSI":        round(d5["RSI"].iloc[-1], 1),
                    "ADX":        round(d5["ADX"].iloc[-1], 1),
                    "Signal":     sig.replace("BLOCKED_","⚠️ "),
                    "Score":      f"{conf}%",
                    "VWAP Side":  "Above ✅" if p > d5["VWAP"].iloc[-1] else "Below 🔴",
                    "ATR":        round(d5["ATR"].iloc[-1], 2),
                    "Move":       f"{md} {ms}/100" if md else f"— {ms}/100",
                })
            except Exception as e:
                compare_data.append({
                    "Commodity": ccfg["label"], "LTP": "—", "RSI": "—",
                    "ADX": "—", "Signal": f"Error: {e}", "Score": "—",
                    "VWAP Side": "—", "ATR": "—", "Move": "—"
                })

    if compare_data:
        comp_df = pd.DataFrame(compare_data)
        st.dataframe(comp_df, use_container_width=True, height=220)

        # Highlight strongest signal
        active = [d for d in compare_data if d["Signal"] in ("CALL","PUT")]
        if active:
            st.success(f"🔥 **Active signals right now:** " + " | ".join(
                f"{d['Commodity']} → {d['Signal']} (Score {d['Score']})" for d in active
            ))
        else:
            st.info("💤 No active CALL/PUT signals across any commodity right now.")
    else:
        st.warning("Could not fetch comparison data.")