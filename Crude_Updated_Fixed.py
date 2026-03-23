# ==========================================
# 🛢️ CRUDE OPTIONS DASHBOARD (FINAL - CAPITAL OPTIMIZED)
# ==========================================

import streamlit as st
from kiteconnect import KiteConnect
import pandas as pd
import ta
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import altair as alt

# CONFIG
API_KEY = "zirmcjssldz9okdc"
ACCESS_TOKEN = "DvmZ6jITMnrbVk5JfbqVXdVhm7g3yBiz"

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

st.set_page_config(layout="wide")
st.title("🛢️CRUDE OPTIONS DASHBOARD")

# =====================
# 🕒 CLOCK (TOP RIGHT)
# =====================
col_left, col_right = st.columns([8,2])

import pytz

with col_right:
    ist = pytz.timezone("Asia/Kolkata")
    current_time = datetime.now(ist)

st_autorefresh(interval=60000, key="refresh")

# ==========
# TRADE LOG
# ==========
if "trade_log" not in st.session_state:
    st.session_state.trade_log = pd.DataFrame(columns=[
        "Time","Signal","Symbol","Strike","Type","LTP","Capital"
    ])

# ==================
# LOAD INSTRUMENTS
# ==================
def load_instruments():
    return pd.DataFrame(kite.instruments("MCX"))

instruments = load_instruments()

def get_token():
    df = instruments[
        (instruments["name"]=="CRUDEOIL") &
        (instruments["segment"]=="MCX-FUT")
    ].copy()

    df = df[df["expiry"]>=pd.Timestamp.today().date()]
    df = df.sort_values("expiry")

    return int(df.iloc[0]["instrument_token"])

# =======
# DATA
# =======
def get_data(token, tf):
    now = datetime.now()
    from_date = now - pd.Timedelta(days=5)

    try:
        data = kite.historical_data(token, from_date, now, tf)
    except:
        data = []

    df = pd.DataFrame(data)
    if not df.empty:
        df.set_index("date", inplace=True)
    return df

# ============
# INDICATORS
# ============
def apply_indicators(df):
    if df.empty:
        return df

    df["EMA9"] = ta.trend.ema_indicator(df["close"], 9)
    df["EMA21"] = ta.trend.ema_indicator(df["close"], 21)
    df["RSI"] = ta.momentum.rsi(df["close"], 14)

    macd = ta.trend.MACD(df["close"])
    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()

    df["date_only"] = df.index.date

    df["cum_vol"] = df.groupby("date_only")["volume"].cumsum()
    df["cum_pv"] = (df["close"] * df["volume"]).groupby(df["date_only"]).cumsum()
    
    df["VWAP"] = df["cum_pv"] / df["cum_vol"]
    
    df.drop(["cum_vol", "cum_pv"], axis=1, inplace=True)

    adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"])
    df["ADX"] = adx.adx()
    df["+DI"] = adx.adx_pos()
    df["-DI"] = adx.adx_neg()

    return df

# ==============
# OPTION CHAIN
# ==============
def get_option_chain(price):
    df = instruments.copy()

    df = df[(df["name"]=="CRUDEOIL") &
            (df["segment"].str.contains("MCX-OPT"))]

    expiry = df["expiry"].min()
    df = df[df["expiry"]==expiry]

    df["diff"] = abs(df["strike"] - price)
    df = df.sort_values("diff").head(60)

    quotes = kite.quote([f"MCX:{x}" for x in df["tradingsymbol"]])

    rows = []
    for _, r in df.iterrows():
        q = quotes.get(f"MCX:{r['tradingsymbol']}", {})
        rows.append({
            "symbol": r["tradingsymbol"],
            "strike": r["strike"],
            "type": r["instrument_type"],
            "ltp": q.get("last_price",0),
            "oi": q.get("oi",0),
            "volume": q.get("volume",0)
        })

    return pd.DataFrame(rows)

# ===========================
# SIGNAL LOGIC (UPDATED)
# ===========================
def advanced_signal(df5, df15):

    if len(df5) < 3 or len(df15) < 3:
        return "NO TRADE"

    l5 = df5.iloc[-1]
    l15 = df15.iloc[-1]

    ema_bull = l15["EMA9"] > l15["EMA21"]
    ema_bear = l15["EMA9"] < l15["EMA21"]

    above_vwap = l5["close"] > l5["VWAP"]
    below_vwap = l5["close"] < l5["VWAP"]

    strong_trend = l5["ADX"] > 25
    rsi = l5["RSI"]

    # 🚫 NO TREND
    if l5["ADX"] < 20:
        return "NO TRADE"

    # 🟢 CALL
    if ema_bull and above_vwap and strong_trend and l5["+DI"] > l5["-DI"] and rsi > 60:
        prev_high = df5["high"].iloc[-2]
        if l5["close"] < prev_high:
            return "NO TRADE"
        return "CALL"

    # 🔴 PUT
    if ema_bear and below_vwap and strong_trend and l5["-DI"] > l5["+DI"] and rsi < 40:
        prev_low = df5["low"].iloc[-2]
        if l5["close"] > prev_low:
            return "NO TRADE"
        return "PUT"

    return "NO TRADE"

# ==============
# TRADE ENGINE
# ==============
def get_trade_options(option_df, signal, price, capital=30000, lot=1):

    if signal == "NO TRADE":
        return {"ATM": None, "ITM": None, "OTM": None, "ideal": 0}

    df = option_df.copy()
    df = df[df["type"] == ("CE" if signal=="CALL" else "PE")]

    df["cost"] = df["ltp"] * 100

    ideal = capital
    lower = ideal * 0.6
    upper = ideal * 1.2

    df_budget = df[(df["cost"] >= lower) & (df["cost"] <= upper)]

    if df_budget.empty:
        df_budget = df[df["cost"] > 0].sort_values("cost").head(10)

    df_budget["dist"] = abs(df_budget["strike"] - price)
    df_budget = df_budget.sort_values("dist")

    atm = df_budget.iloc[0:1]

    if signal=="CALL":
        itm = df_budget[df_budget["strike"]<price].head(1)
        otm = df_budget[df_budget["strike"]>price].head(1)
    else:
        itm = df_budget[df_budget["strike"]>price].head(1)
        otm = df_budget[df_budget["strike"]<price].head(1)

    def pick(d):
        return d.iloc[0] if not d.empty else None

    return {
        "ATM": pick(atm),
        "ITM": pick(itm),
        "OTM": pick(otm),
        "ideal": round(ideal,2)
    }

# =======
# MAIN
# =======
token = get_token()

df5 = apply_indicators(get_data(token,"5minute"))
df15 = apply_indicators(get_data(token,"15minute"))

if df5.empty:
    st.error("No data")
    st.stop()

price = df5["close"].iloc[-1]
option_df = get_option_chain(price)

signal = advanced_signal(df5, df15)
trades = get_trade_options(option_df, signal, price)

# ============
# SAVE TRADE
# ============
if signal != "NO TRADE" and trades["ATM"] is not None:
    t = trades["ATM"]

    new_row = pd.DataFrame([{
        "Time": datetime.now().strftime("%H:%M:%S"),
        "Signal": signal,
        "Symbol": t["symbol"],
        "Strike": t["strike"],
        "Type": t["type"],
        "LTP": float(t["ltp"]),
        "Capital": float(t["ltp"] * 100)
    }])

    if st.session_state.trade_log.empty:
        st.session_state.trade_log = new_row
    else:
        if st.session_state.trade_log.iloc[-1]["Symbol"] != t["symbol"]:
            st.session_state.trade_log = pd.concat(
                [st.session_state.trade_log, new_row],
                ignore_index=True
            ).tail(50)

# ======
# UI
# ======
c1,c2,c3,c4,c5 = st.columns(5)

c1.metric("Price", round(price,2))
c2.metric("Signal", signal)
c3.metric("RSI", round(df5["RSI"].iloc[-1],2))
c4.metric("ADX", round(df5["ADX"].iloc[-1],2))
c5.metric("VWAP Side", "Above" if price > df5["VWAP"].iloc[-1] else "Below")

# RSI
rsi_val = df5["RSI"].iloc[-1]

if rsi_val > 60:
    st.success(f"🟢 Strong Bullish RSI: {round(rsi_val,2)}")
elif rsi_val < 40:
    st.error(f"🔴 Strong Bearish RSI: {round(rsi_val,2)}")
else:
    st.warning(f"🟡 Neutral RSI: {round(rsi_val,2)}")

# ===============
# TRADE DISPLAY
# ===============
st.subheader("🎯 Trade Suggestions")

if signal == "NO TRADE":
    st.warning("🚫 No Trade Zone")
else:
    st.info(f"💰 Capital: ₹30000 | Ideal Premium: ~₹{trades['ideal']}")

def show(label,t):
    if t is None:
        st.warning(f"{label}: Not available in budget")
        return

    st.success(f"""
{label} ({signal})

{t['symbol']}
Strike: {t['strike']}
LTP: {t['ltp']}

💰 Premium: ₹{round(t['ltp'])}
💰 Cost: ₹{round(t['ltp']*100)}

SL: {round(t['ltp']*0.7,2)}
T1: {round(t['ltp']*1.5,2)}
T2: {round(t['ltp']*2,2)}
""")

if signal != "NO TRADE":
    col1,col2,col3 = st.columns(3)
    with col1: show("ATM",trades["ATM"])
    with col2: show("ITM",trades["ITM"])
    with col3: show("OTM",trades["OTM"])

# ===============
# TRADE HISTORY
# ===============
st.subheader("📋 Trade History")
st.dataframe(st.session_state.trade_log.iloc[::-1], width='stretch')

# ========
# CHART
# ========
st.subheader("📈 Price Chart")
chart_data = df5.reset_index()

chart = alt.Chart(chart_data).transform_fold(
    ["close", "EMA9", "EMA21", "VWAP"],
    as_=["Metric", "Value"]
).mark_line().encode(
    x="date:T",
    y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
    color="Metric:N"
).properties(height=400)

st.altair_chart(chart, width='stretch')

# ===============
# OPTION CHAIN
# ===============
st.subheader("📊 Option Chain")
st.dataframe(option_df, width='stretch')