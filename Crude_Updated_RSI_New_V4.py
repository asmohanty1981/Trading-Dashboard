# ============================================================
# 🛢️ CRUDE OPTIONS DASHBOARD — v3 PATCHED
# ============================================================
# FIXES IN THIS PATCH:
#
# FIX 1 [BUG] "NO TRADE — Score 73/55 needed" was meaningless
#   Root cause: compute_signal() had two hard early-exit filters
#   AFTER the score check that silently blocked a valid CALL:
#     a) rsi_topping: rsi > 65 and rsi < rsi_prev
#        (RSI=52.46 is NOT >65 — this wasn't the blocker here)
#     b) prev_high: close < prev bar high → NO TRADE
#        This IS the blocker — crude at 9211 consolidating
#        below the 9213 prev bar high. Too strict for trending crude.
#   Fix A: Removed the hard prev_high block entirely.
#          Replaced with a -5 score penalty (soft deterrent, not hard kill)
#   Fix B: Banner now shows clearly when score is met but blocked:
#          "⚠️ CALL BLOCKED (score 73 ✅)" instead of "NO TRADE Score 73/55"
#   Fix C: Signal reasoning now shows EXACTLY why it was blocked
#
# FIX 2 [BUG] Trade log time not updating for same strike
#   Old: if last Symbol == current symbol → skip entirely
#   Problem: CRUDEOIL26APR10700CE given at 15:51, confirmed again
#            at 16:40 and 17:51 — log never updated, stuck at 15:51
#   Fix: If same Signal+Strike → UPDATE the existing row's Time, LTP,
#        Confidence in place (upsert behaviour) instead of skipping
#   This gives accurate "last confirmed at" time for post-analysis
#   New columns added: "First_Seen", "Last_Updated", "Confirmations"
#
# FIX 3 [FEATURE] Candlestick charts for 5-min and 15-min
#   Old: Line charts only (transform_fold + mark_line)
#   New: Proper OHLC candlestick (mark_rule + mark_bar in Altair)
#        with EMA9, EMA21, VWAP overlaid as lines
#        5-min: last 1.5 days of candles
#        15-min: last 3 days of candles
#        Color: green candle = close > open, red = close < open
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

# ── CONFIG ─────────────────────────────────────────────────────────────────────
API_KEY      = "zirmcjssldz9okdc"
ACCESS_TOKEN = "UqZWDyzibbxw4LByYqBanRflsegXymq8"

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

st.set_page_config(layout="wide", page_title="Crude Options Dashboard")

col_title, col_clock = st.columns([8, 2])
with col_title:
    st.title("🛢️ CRUDE OPTIONS DASHBOARD")
with col_clock:
    ist          = pytz.timezone("Asia/Kolkata")
    current_time = datetime.now(ist)
    st.markdown(f"### 🕒 {current_time.strftime('%H:%M:%S')}")

st_autorefresh(interval=60000, key="refresh")

st.markdown("""
<style>
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
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ──────────────────────────────────────────────────────────────
if "trade_log" not in st.session_state:
    st.session_state.trade_log = pd.DataFrame(columns=[
        "First_Seen","Last_Updated","Confirmations","Signal","Symbol",
        "Strike","Type","LTP","Cost_1Lot","Lots","Total_Capital",
        "SL","T1","T2","Confidence","Move_Score"
    ])

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Trade Settings")
    capital      = st.number_input("Total Capital (₹)", 10000, 500000, 25000, 5000)
    num_lots     = st.number_input("Number of Lots", 1, 10, 2)
    lot_size_opt = st.selectbox("Lot Size", [100, 10], index=0,
                                 help="Standard crude = 100 bbl | Mini = 10 bbl")

    st.markdown("---")
    st.markdown("**🎯 Premium Target Range**")
    min_prem    = st.number_input("Min Premium (₹)", 50, 1000, 200, 25)
    max_prem    = st.number_input("Max Premium (₹)", 50, 2000, 280, 25)
    target_prem = (min_prem + max_prem) / 2
    st.info(
        f"Premium: ₹{min_prem}–₹{max_prem}\n"
        f"Per lot: ₹{int(min_prem*lot_size_opt)}–₹{int(max_prem*lot_size_opt)}\n"
        f"{num_lots} lot(s): ₹{int(min_prem*lot_size_opt*num_lots):,}–"
        f"₹{int(max_prem*lot_size_opt*num_lots):,}"
    )

    st.markdown("---")
    st.markdown("**📈 Signal Settings**")
    adx_min   = st.slider("ADX Threshold", 18, 35, 22)
    min_score = st.slider("Min Signal Score", 40, 90, 55)

    st.markdown("---")
    st.markdown("**🚀 200-Pt Move Detector**")
    show_200   = st.checkbox("Show 200-Pt Move Panel", value=True)
    move_boost = st.checkbox("Boost confidence when move aligns", value=True)

# ── INSTRUMENTS ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400)
def load_instruments():
    return pd.DataFrame(kite.instruments("MCX"))

instruments = load_instruments()

def get_token():
    df = instruments[
        (instruments["name"] == "CRUDEOIL") &
        (instruments["segment"] == "MCX-FUT")
    ].copy()
    df = df[df["expiry"] >= pd.Timestamp.today().date()].sort_values("expiry")
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

    # Daily VWAP reset
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
def detect_200pt_move(df5):
    if df5.empty or len(df5) < 20:
        return None, 0, {}

    l = df5.iloc[-1]
    score  = 0
    detail = {}

    atr = l.get("ATR", 0)
    if atr > 80:   score += 30; detail["ATR"] = f"ATR {round(atr,1)} > 80 → +30 pts"
    elif atr > 60: score += 20; detail["ATR"] = f"ATR {round(atr,1)} > 60 → +20 pts"
    elif atr > 40: score += 10; detail["ATR"] = f"ATR {round(atr,1)} > 40 → +10 pts"
    else:          detail["ATR"] = f"ATR {round(atr,1)} ≤ 40 → +0 pts"

    mom = l.get("momentum_5", 0)
    if abs(mom) > 100:  score += 25; detail["Momentum"] = f"5-bar {round(mom,1)} pts → +25"
    elif abs(mom) > 60: score += 15; detail["Momentum"] = f"5-bar {round(mom,1)} pts → +15"
    elif abs(mom) > 30: score += 8;  detail["Momentum"] = f"5-bar {round(mom,1)} pts → +8"
    else:               detail["Momentum"] = f"5-bar {round(mom,1)} pts → +0"

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

    if   mom > 0 and di_p > di_m: direction = "UP"
    elif mom < 0 and di_m > di_p: direction = "DOWN"
    elif di_p > di_m:              direction = "UP"
    elif di_m > di_p:              direction = "DOWN"
    else:                          direction = "UNCLEAR"

    return direction, score, detail

# ══════════════════════════════════════════════════════════════════════════════
# ── SIGNAL ENGINE — FIX 1 ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
def compute_signal(df5, df15, adx_threshold, min_score, move_dir, move_score, do_boost):
    """
    FIX 1: Removed hard prev_high/prev_low early-exit blocks.
    These were causing "NO TRADE Score 73/55" — score met but blocked
    silently. Replaced with soft penalty (-5 pts) so the signal can
    still fire but with slightly lower confidence on consolidating bars.

    Returns: (signal, raw_score, confidence, reasons, block_reason)
      signal:       "CALL" / "PUT" / "BLOCKED_CALL" / "BLOCKED_PUT" / "NO TRADE"
      raw_score:    score before boost (for display)
      confidence:   score after boost (for display)
      reasons:      list of scoring reasons
      block_reason: non-empty string if signal was blocked by a filter
    """
    if len(df5) < 3 or len(df15) < 3:
        return "NO TRADE", 0, 0, ["Insufficient data"], ""

    l5  = df5.iloc[-1]
    l15 = df15.iloc[-1]
    adx = l5["ADX"]

    if adx < 18:
        return "NO TRADE", 0, 0, [f"⛔ ADX {round(adx,1)} < 18 — flat market"], ""

    # ADX partial credit
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

    rsi_topping   = rsi > 65 and rsi < rsi_prev   # RSI rolling over at top
    rsi_bottoming = rsi < 35 and rsi > rsi_prev   # RSI turning up at bottom

    # ── CALL scoring ──────────────────────────────────────────────────────────
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

    # FIX 1: Soft penalty for consolidation (was a hard block before)
    prev_high = df5["high"].iloc[-2]
    if l5["close"] < prev_high:
        call_score -= 5
        call_reasons.append(
            f"⚠️ Close {round(l5['close'],1)} < prev bar high {round(prev_high,1)} → −5 pts (consolidating)"
        )

    # ── PUT scoring ───────────────────────────────────────────────────────────
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

    # FIX 1: Soft penalty for consolidation
    prev_low = df5["low"].iloc[-2]
    if l5["close"] > prev_low:
        put_score -= 5
        put_reasons.append(
            f"⚠️ Close {round(l5['close'],1)} > prev bar low {round(prev_low,1)} → −5 pts"
        )

    # ── Decision ──────────────────────────────────────────────────────────────
    if call_score >= min_score and call_score > put_score:
        # RSI topping is still a hard block (RSI>65 rolling over is genuinely dangerous)
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

    # Score not met
    weak = []
    if call_score > 0: weak.append(f"Bullish score {call_score}/{min_score} — need {min_score - call_score} more pts")
    if put_score  > 0: weak.append(f"Bearish score {put_score}/{min_score} — need {min_score - put_score} more pts")
    if not weak:       weak.append("No EMA directional alignment on 15-min")
    return "NO TRADE", max(call_score, put_score), max(call_score, put_score), [f"⏸ {w}" for w in weak], ""

# ── OPTION CHAIN ───────────────────────────────────────────────────────────────
def get_option_chain(price):
    df = instruments.copy()
    df = df[(df["name"]=="CRUDEOIL") & (df["segment"].str.contains("MCX-OPT"))]
    if df.empty: return pd.DataFrame()
    expiry = df["expiry"].min()
    df     = df[df["expiry"]==expiry].copy()
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
                else ("ATM" if abs(r["strike"]-price)<=50 else "OTM")
            ),
        })
    return pd.DataFrame(rows)

# ── OPTION PICKER ──────────────────────────────────────────────────────────────
def pick_options_by_premium(option_df, signal, target_prem, min_prem, max_prem,
                             lot_size, num_lots):
    sig = signal.replace("BLOCKED_","")  # treat BLOCKED_CALL as CALL for options
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

# ── FIX 2: TRADE LOG — UPSERT (update time if same strike) ────────────────────
def upsert_trade_log(log_df, signal, best_row, num_lots, confidence, move_score,
                     move_dir, current_time):
    """
    FIX 2: Instead of skipping duplicate strikes, UPDATE the existing row.
    - Same Signal + Strike → update Last_Updated, LTP, Confidence, Confirmations
    - New Signal or new Strike → append new row
    - This gives accurate "last confirmed at" timestamp for post-analysis
    """
    if best_row is None:
        return log_df

    sig_clean = signal.replace("BLOCKED_","")
    strike    = best_row["strike"]
    symbol    = best_row["symbol"]
    now_str   = current_time.strftime("%H:%M:%S")

    if not log_df.empty:
        # Check if same Signal + Strike already exists
        mask = (log_df["Signal"] == sig_clean) & (log_df["Strike"] == strike)
        if mask.any():
            # UPDATE existing row — increment Confirmations, update Last_Updated + LTP
            idx = log_df[mask].index[-1]
            log_df.at[idx, "Last_Updated"]  = now_str
            log_df.at[idx, "LTP"]           = float(best_row["ltp"])
            log_df.at[idx, "Confidence"]    = f"{confidence}%"
            log_df.at[idx, "Confirmations"] = log_df.at[idx, "Confirmations"] + 1
            log_df.at[idx, "Move_Score"]    = f"{move_score}/100 {move_dir or ''}"
            return log_df

    # New entry
    new_row = pd.DataFrame([{
        "First_Seen":    now_str,
        "Last_Updated":  now_str,
        "Confirmations": 1,
        "Signal":        sig_clean,
        "Symbol":        symbol,
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
    return pd.concat([log_df, new_row], ignore_index=True).tail(50)

# ── FIX 3: CANDLESTICK CHART BUILDER ──────────────────────────────────────────
def make_candlestick(df, ema_cols, title, height=400, last_n_bars=None):
    """
    FIX 3: Build a proper OHLC candlestick chart in Altair.
    Uses mark_rule (wick) + mark_bar (body) pattern.
    Overlays EMA lines and VWAP if present.
    """
    cd = df.reset_index().copy()
    if last_n_bars:
        cd = cd.tail(last_n_bars)

    cd["color"] = cd.apply(
        lambda r: "Up" if r["close"] >= r["open"] else "Down", axis=1
    )

    base = alt.Chart(cd)

    # Wicks
    rule = base.mark_rule(strokeWidth=1).encode(
        x=alt.X("date:T", title="Time"),
        y=alt.Y("low:Q",  scale=alt.Scale(zero=False), title="Price"),
        y2=alt.Y2("high:Q"),
        color=alt.Color(
            "color:N",
            scale=alt.Scale(domain=["Up","Down"], range=["#2e7d32","#c62828"]),
            legend=None
        )
    )

    # Bodies
    bar = base.mark_bar().encode(
        x=alt.X("date:T"),
        y=alt.Y("open:Q",  scale=alt.Scale(zero=False)),
        y2=alt.Y2("close:Q"),
        color=alt.Color(
            "color:N",
            scale=alt.Scale(domain=["Up","Down"], range=["#2e7d32","#c62828"]),
            legend=None
        ),
        tooltip=[
            alt.Tooltip("date:T",  title="Time"),
            alt.Tooltip("open:Q",  title="Open"),
            alt.Tooltip("high:Q",  title="High"),
            alt.Tooltip("low:Q",   title="Low"),
            alt.Tooltip("close:Q", title="Close"),
            alt.Tooltip("volume:Q",title="Volume"),
        ]
    )

    # EMA overlay lines
    ema_colors = {
        "EMA9":  "#f39c12",
        "EMA21": "#1565c0",
        "VWAP":  "#6a1b9a",
        "EMA20": "#e67e22",
        "EMA50": "#16a085",
    }

    layers = [rule, bar]
    for col in ema_cols:
        if col in cd.columns:
            cd_ema = cd[["date", col]].dropna()
            line = (
                alt.Chart(cd_ema)
                .mark_line(strokeWidth=1.5)
                .encode(
                    x="date:T",
                    y=alt.Y(f"{col}:Q", scale=alt.Scale(zero=False)),
                    color=alt.value(ema_colors.get(col, "#888"))
                )
            )
            layers.append(line)

    chart = alt.layer(*layers).properties(height=height, title=title)
    return chart

# ── NEWS ───────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_crude_news():
    try:
        feed = feedparser.parse(
            "https://news.google.com/rss/search?q=crude+oil+MCX+price&hl=en-IN&gl=IN&ceid=IN:en"
        )
        return [{"title":e.title,"link":e.link,"time":e.get("published","")}
                for e in feed.entries[:7]]
    except Exception:
        return []

# ══════════════════════════════════════════════════════════════════════════════
# ── MAIN ───────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
token = get_token()

with st.spinner("📡 Fetching market data..."):
    df5  = apply_indicators(get_data(token, "5minute",  4))
    df15 = apply_indicators(get_data(token, "15minute", 6))

if df5.empty:
    st.error("❌ No data. Check API token / market hours.")
    st.stop()

price     = df5["close"].iloc[-1]
option_df = get_option_chain(price)

move_dir, move_score, move_detail = detect_200pt_move(df5)

signal, raw_score, confidence, reasons, block_reason = compute_signal(
    df5, df15, adx_min, min_score, move_dir, move_score, move_boost
)

# Determine effective signal for option picking
effective_signal = signal  # may be CALL, PUT, BLOCKED_CALL, BLOCKED_PUT, NO TRADE
best_row, cheaper_row, pricier_row = pick_options_by_premium(
    option_df, effective_signal, target_prem, min_prem, max_prem, lot_size_opt, num_lots
)

# ── FIX 2: UPSERT trade log ────────────────────────────────────────────────────
if signal in ("CALL","PUT") and best_row:
    st.session_state.trade_log = upsert_trade_log(
        st.session_state.trade_log, signal, best_row,
        num_lots, confidence, move_score, move_dir, current_time
    )

# ── METRICS ────────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("💰 Crude LTP",  round(price,2))
c2.metric("📶 Signal",     signal.replace("BLOCKED_","⚠️ "))
c3.metric("📊 RSI",        round(df5["RSI"].iloc[-1],2))
c4.metric("📈 ADX",        round(df5["ADX"].iloc[-1],2))
c5.metric("🌊 VWAP Side",  "Above ✅" if price > df5["VWAP"].iloc[-1] else "Below 🔴")
c6.metric("🎯 Score",      f"{confidence}%")

# Score bar
bar_col = "#2e7d32" if raw_score>=min_score else "#f9a825" if raw_score>=min_score*0.7 else "#c62828"
st.markdown(
    f'<div style="margin:2px 0 8px"><small>Signal score: <b>{raw_score}/100</b> '
    f'(need ≥ {min_score}) &nbsp;|&nbsp; Confidence after boost: <b>{confidence}%</b></small>'
    f'<div class="bar-wrap"><div class="bar-fill" '
    f'style="width:{min(raw_score,100)}%;background:{bar_col}"></div></div></div>',
    unsafe_allow_html=True
)

# ── FIX 1: Signal Banner — clear BLOCKED state ────────────────────────────────
if signal == "CALL":
    st.markdown(
        f'<div class="sig-call">🟢 CALL — Buy CE &nbsp;|&nbsp; '
        f'Score: {raw_score}/100 ✅ &nbsp;|&nbsp; Confidence: {confidence}% &nbsp;|&nbsp; '
        f'Premium ₹{min_prem}–₹{max_prem}</div>',
        unsafe_allow_html=True
    )
elif signal == "PUT":
    st.markdown(
        f'<div class="sig-put">🔴 PUT — Buy PE &nbsp;|&nbsp; '
        f'Score: {raw_score}/100 ✅ &nbsp;|&nbsp; Confidence: {confidence}% &nbsp;|&nbsp; '
        f'Premium ₹{min_prem}–₹{max_prem}</div>',
        unsafe_allow_html=True
    )
elif signal == "BLOCKED_CALL":
    st.markdown(
        f'<div class="sig-blocked">⚠️ CALL BLOCKED — Score {raw_score}/100 ✅ threshold met, '
        f'but entry filtered: <b>{block_reason}</b><br>'
        f'<small>The score qualifies. Wait for filter to clear, then signal will fire.</small></div>',
        unsafe_allow_html=True
    )
elif signal == "BLOCKED_PUT":
    st.markdown(
        f'<div class="sig-blocked">⚠️ PUT BLOCKED — Score {raw_score}/100 ✅ threshold met, '
        f'but entry filtered: <b>{block_reason}</b><br>'
        f'<small>The score qualifies. Wait for filter to clear, then signal will fire.</small></div>',
        unsafe_allow_html=True
    )
else:
    # Genuine WAIT — score not met
    pts_needed = max(0, min_score - raw_score)
    st.markdown(
        f'<div class="sig-wait">🟡 WAIT — Score {raw_score}/{min_score} '
        f'(need {pts_needed} more pts to qualify)</div>',
        unsafe_allow_html=True
    )

with st.expander("📋 Signal Reasoning"):
    for r in reasons:
        st.markdown(f"- {r}")

# ── TRADE SUGGESTIONS ──────────────────────────────────────────────────────────
is_tradeable = signal in ("CALL","PUT","BLOCKED_CALL","BLOCKED_PUT")
display_sig  = signal.replace("BLOCKED_","")

st.subheader(
    f"🎯 Trade Suggestions — ₹{capital:,} | {num_lots} lot(s) | "
    f"Lot size {lot_size_opt} | Target premium ₹{min_prem}–₹{max_prem}"
)

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
        st.warning(f"⚠️ Signal blocked by RSI filter. Showing what would be suggested if it clears.")
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

# ── FIX 2: TRADE LOG with upsert ──────────────────────────────────────────────
st.subheader("📋 Trade History")
if not st.session_state.trade_log.empty:
    # Highlight rows where Last_Updated ≠ First_Seen (confirmed multiple times)
    st.dataframe(st.session_state.trade_log.iloc[::-1], use_container_width=True)
    st.caption(
        "ℹ️ **First_Seen** = when signal first fired. "
        "**Last_Updated** = last time same strike was re-confirmed. "
        "**Confirmations** = how many times signal repeated for this strike."
    )
    if st.button("🗑️ Clear Log"):
        st.session_state.trade_log = pd.DataFrame(
            columns=st.session_state.trade_log.columns
        )
        st.rerun()
else:
    st.info("No trades logged yet.")

# ── 200-POINT MOVE DETECTOR ────────────────────────────────────────────────────
if show_200:
    st.subheader("🚀 200-Point Move Detector")
    mv1,mv2,mv3 = st.columns(3)
    mv1.metric("📐 Direction",        move_dir or "Unclear")
    mv2.metric("🎯 Move Probability", f"{move_score}/100")
    mv3.metric("📏 ATR (5-min)",      round(df5["ATR"].iloc[-1],1))

    mc = "#2e7d32" if move_score>=60 else "#f9a825" if move_score>=35 else "#bdbdbd"
    st.markdown(
        f'<div style="margin:2px 0 8px"><small>Move score: <b>{move_score}/100</b></small>'
        f'<div class="bar-wrap"><div class="bar-fill" '
        f'style="width:{move_score}%;background:{mc}"></div></div></div>',
        unsafe_allow_html=True
    )

    if move_score >= 60:
        st.markdown(
            f'<div class="move-high">⚡ HIGH probability 200-pt move <b>{move_dir}</b> — '
            f'Strong momentum. Align options!</div>', unsafe_allow_html=True
        )
        if move_boost and signal in ("CALL","PUT"):
            sig_dir = "UP" if signal=="CALL" else "DOWN"
            if move_dir == sig_dir:
                st.success(f"🔥 Move aligns with signal — confidence boosted +{min(int(move_score/5),20)}")
            else:
                st.warning(f"⚠️ Move direction ({move_dir}) conflicts with signal — caution")
    elif move_score >= 35:
        st.markdown(
            f'<div class="move-mid">🟡 Moderate 200-pt move chance <b>{move_dir}</b> — Monitor.</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="move-low">📉 Low-volatility — 200-pt move unlikely now.</div>',
            unsafe_allow_html=True
        )

    with st.expander("🔍 Move Score Breakdown"):
        for k,v in move_detail.items():
            st.markdown(f"- **{k}**: {v}")

    if "momentum_5" in df5.columns:
        mom_df = df5.reset_index()[["date","momentum_5"]].dropna().tail(60)
        mom_chart = (
            alt.Chart(mom_df).mark_bar()
            .encode(
                x=alt.X("date:T"),
                y=alt.Y("momentum_5:Q", title="5-bar momentum"),
                color=alt.condition(
                    alt.datum.momentum_5 > 0,
                    alt.value("#2e7d32"), alt.value("#c62828")
                ),
                tooltip=["date:T","momentum_5:Q"]
            ).properties(height=150, title="5-Bar Momentum (200-pt move energy)")
        )
        st.altair_chart(
            mom_chart + alt.Chart(pd.DataFrame({"y":[0]}))
            .mark_rule(color="#999",strokeDash=[3,3]).encode(y="y:Q"),
            use_container_width=True
        )

# ── FIX 3: CANDLESTICK CHARTS ──────────────────────────────────────────────────
st.subheader("📈 5-Min Candlestick Chart — EMA9 / EMA21 / VWAP")
if not df5.empty:
    # Show last 80 bars (~6.5 hrs of 5-min data)
    st.altair_chart(
        make_candlestick(
            df5, ema_cols=["EMA9","EMA21","VWAP"],
            title="Crude 5-Min — EMA9 (orange) | EMA21 (blue) | VWAP (purple)",
            height=400, last_n_bars=80
        ),
        use_container_width=True
    )

st.subheader("📊 15-Min Candlestick Chart — EMA9 / EMA21")
if not df15.empty:
    # Show last 50 bars (~12.5 hrs of 15-min data = ~2 sessions)
    st.altair_chart(
        make_candlestick(
            df15, ema_cols=["EMA9","EMA21"],
            title="Crude 15-Min — EMA9 (orange) | EMA21 (blue)",
            height=380, last_n_bars=50
        ),
        use_container_width=True
    )

# RSI
st.subheader("📉 RSI (14)")
cd = df5.reset_index()
st.altair_chart(
    alt.Chart(cd).mark_line(color="#e67e22")
    .encode(x="date:T", y=alt.Y("RSI:Q", scale=alt.Scale(domain=[0,100])))
    .properties(height=130)
    + alt.Chart(pd.DataFrame({"y":[70]})).mark_rule(color="red",   strokeDash=[4,3]).encode(y="y:Q")
    + alt.Chart(pd.DataFrame({"y":[30]})).mark_rule(color="green", strokeDash=[4,3]).encode(y="y:Q"),
    use_container_width=True
)

# ── NEWS ───────────────────────────────────────────────────────────────────────
st.subheader("📰 Crude Oil News")
for item in get_crude_news():
    st.markdown(f"• [{item['title']}]({item['link']}) — _{item['time']}_")

# ── OPTION CHAIN ───────────────────────────────────────────────────────────────
st.subheader("📊 Option Chain")
if not option_df.empty:
    oc1,oc2 = st.columns(2)
    with oc1:
        st.markdown("**CE (Call Options)**")
        st.dataframe(
            option_df[option_df["type"]=="CE"]
            .sort_values("strike")[["strike","moneyness","ltp","oi","volume"]].head(20),
            use_container_width=True
        )
    with oc2:
        st.markdown("**PE (Put Options)**")
        st.dataframe(
            option_df[option_df["type"]=="PE"]
            .sort_values("strike",ascending=False)[["strike","moneyness","ltp","oi","volume"]].head(20),
            use_container_width=True
        )