# ==========================================
# 🏦 OPTIONS DASHBOARD (SENSEX + NIFTY + BANKNIFTY + FINNIFTY)
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
ACCESS_TOKEN = "DaU1Ie6Lt977zpdNWUu8f12Jvw9VLJxN"

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

# AUTO REFRESH
st_autorefresh(interval=60000, key="refresh")

# ==========================================
# UI STYLE
# ==========================================
st.set_page_config(layout="wide")

st.markdown("""
<style>
.main {background-color:#f5f7fa;}
h1 {text-align:center;}

[data-testid="stMetricValue"] {
    font-weight: 800 !important;
    color: #111 !important;
    font-size: 22px !important;
}

[data-testid="stMetricLabel"] {
    font-weight: 600 !important;
    color: #444 !important;
}

.trade-box {
    padding:20px;
    border-radius:12px;
    font-size:16px;
    font-weight:500;
}
buy-box {background:#e6f4ea;border-left:6px solid green;}
sell-box {background:#fdecea;border-left:6px solid red;}
wait-box {background:#fff4e5;border-left:6px solid orange;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# LOAD INSTRUMENTS
# ==========================================
@st.cache_data(ttl=86400)
def load_instruments():
    return pd.DataFrame(kite.instruments())

instruments = load_instruments()

# ==========================================
# TOKEN
# ==========================================
def get_token(symbol):

    if symbol == "SENSEX":
        df = instruments[
            (instruments["name"] == "SENSEX") &
            (instruments["segment"] == "INDICES")
        ]
        return int(df.iloc[0]["instrument_token"])

    elif symbol == "NIFTY":
        df = instruments[
            (instruments["name"] == "NIFTY 50") &
            (instruments["segment"] == "INDICES")
        ]
        return int(df.iloc[0]["instrument_token"])

    elif symbol == "BANKNIFTY":
        df = instruments[
            (instruments["name"] == "NIFTY BANK") &
            (instruments["segment"] == "INDICES")
        ]
        return int(df.iloc[0]["instrument_token"])

    elif symbol == "FINNIFTY":
        df = instruments[
            (instruments["name"] == "NIFTY FIN SERVICE") &
            (instruments["segment"] == "INDICES")
        ]
        return int(df.iloc[0]["instrument_token"])

    elif symbol == "NIFTY FUT":
        df = instruments[
            (instruments["name"] == "NIFTY") &
            (instruments["segment"] == "NFO-FUT")
        ]
        df = df.sort_values("expiry")
        return int(df.iloc[0]["instrument_token"])

# ==========================================
# DATA
# ==========================================
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

# ==========================================
# INDICATORS
# ==========================================
def apply_indicators(df):
    if df.empty:
        return df

    df["EMA20"] = ta.trend.ema_indicator(df["close"], 20)
    df["EMA50"] = ta.trend.ema_indicator(df["close"], 50)
    df["RSI"] = ta.momentum.rsi(df["close"], 14)

    macd = ta.trend.MACD(df["close"])
    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()

    df["VWAP"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()

    df["EMA9"] = ta.trend.ema_indicator(df["close"], 9)
    df["EMA21"] = ta.trend.ema_indicator(df["close"], 21)

    try:
        if len(df) > 30:
            adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"])
            df["ADX"] = adx.adx()
            df["+DI"] = adx.adx_pos()
            df["-DI"] = adx.adx_neg()
        else:
            df["ADX"] = 0
            df["+DI"] = 0
            df["-DI"] = 0
    except:
        df["ADX"] = 0
        df["+DI"] = 0
        df["-DI"] = 0

    return df

# ==========================================
# ✅ ADD ONLY (SUPPORT / RESISTANCE)
# ==========================================
def calculate_support_resistance(df, window=20):
    if df.empty or len(df) < window:
        return None, None
    support = df["low"].rolling(window).min().iloc[-1]
    resistance = df["high"].rolling(window).max().iloc[-1]
    return support, resistance

def calculate_oi_levels(option_df):
    if option_df.empty or "type" not in option_df.columns:
        return None, None

    pe_df = option_df[option_df["type"] == "PE"]
    ce_df = option_df[option_df["type"] == "CE"]

    support = pe_df.loc[pe_df["oi"].idxmax()]["strike"] if not pe_df.empty else None
    resistance = ce_df.loc[ce_df["oi"].idxmax()]["strike"] if not ce_df.empty else None

    return support, resistance

# ==========================================
# OPTION CHAIN
# ==========================================
def get_option_chain(symbol, price):

    if symbol == "SENSEX":
        exch = "BFO"
        seg = "BFO-OPT"
        name = "SENSEX"
    elif symbol == "BANKNIFTY":
        exch = "NFO"
        seg = "NFO-OPT"
        name = "BANKNIFTY"
    elif symbol == "FINNIFTY":
        exch = "NFO"
        seg = "NFO-OPT"
        name = "FINNIFTY"
    else:
        exch = "NFO"
        seg = "NFO-OPT"
        name = "NIFTY"

    df = pd.DataFrame(kite.instruments(exch))

    expiry = df[
        (df["name"] == name) &
        (df["segment"] == seg)
    ]["expiry"].min()

    df = df[
        (df["name"] == name) &
        (df["expiry"] == expiry)
    ].copy()

    df["diff"] = abs(df["strike"] - price)
    df = df.sort_values("diff").head(30)

    quotes = kite.quote([f"{exch}:{x}" for x in df["tradingsymbol"]])

    rows = []
    for _, r in df.iterrows():
        q = quotes.get(f"{exch}:{r['tradingsymbol']}", {})
        rows.append({
            "strike": r["strike"],
            "type": r["instrument_type"],
            "ltp": q.get("last_price", 0),
            "oi": q.get("oi", 0),
            "oi_change": q.get("oi_day_high", 0) - q.get("oi_day_low", 0),
            "volume": q.get("volume", 0)
        })

    return pd.DataFrame(rows)

# ==========================================
# PCR / SMART MONEY / SIGNAL (UNCHANGED)
# ==========================================
def calculate_pcr(option_df):
    if option_df.empty or "type" not in option_df.columns:
        return 1
    ce_oi = option_df[option_df["type"] == "CE"]["oi"].sum()
    pe_oi = option_df[option_df["type"] == "PE"]["oi"].sum()
    return pe_oi / ce_oi if ce_oi != 0 else 1

def smart_money_flow(option_df):
    if option_df.empty or "type" not in option_df.columns:
        return "No Data"
    ce_oi = option_df[option_df["type"] == "CE"]["oi"].sum()
    pe_oi = option_df[option_df["type"] == "PE"]["oi"].sum()
    ce_vol = option_df[option_df["type"] == "CE"]["volume"].sum()
    pe_vol = option_df[option_df["type"] == "PE"]["volume"].sum()
    pcr = pe_oi / ce_oi if ce_oi != 0 else 0

    if pcr > 1.2 and pe_vol > ce_vol:
        return "🟢 FII Bullish (Put Writing)"
    elif pcr < 0.8 and ce_vol > pe_vol:
        return "🔴 FII Bearish (Call Writing)"
    elif pcr > 1:
        return "🟡 Mild Bullish"
    elif pcr < 1:
        return "🟡 Mild Bearish"
    return "⚪ Neutral"

def advanced_signal(df5, df15, option_df):
    if df5.empty or df15.empty:
        return "WAIT"

    if option_df.empty or "type" not in option_df.columns:
        return "WAIT"

    l5 = df5.iloc[-1]
    l15 = df15.iloc[-1]
    pcr = calculate_pcr(option_df)

    trend_bullish = (
        l5["EMA20"] > l5["EMA50"] and
        l5["RSI"] > 55 and
        l5["MACD"] > l5["MACD_SIGNAL"] and
        pcr > 1
    )

    trend_bearish = (
        l5["EMA20"] < l5["EMA50"] and
        l5["RSI"] < 45 and
        l5["MACD"] < l5["MACD_SIGNAL"] and
        pcr < 1
    )

    price_bullish = (
        l15["EMA9"] > l15["EMA21"] and
        l5["close"] > l15["high"] and
        l5["close"] > l5["VWAP"] and
        l5["ADX"] > 25 and
        l5["+DI"] > l5["-DI"]
    )

    price_bearish = (
        l15["EMA9"] < l15["EMA21"] and
        l5["close"] < l15["low"] and
        l5["close"] < l5["VWAP"] and
        l5["ADX"] > 25 and
        l5["-DI"] > l5["+DI"]
    )

    if trend_bullish and price_bullish:
        return "CALL"
    elif trend_bearish and price_bearish:
        return "PUT"
    elif trend_bullish or price_bullish:
        return "CALL"
    elif trend_bearish or price_bearish:
        return "PUT"
    return "WAIT"

# ==========================================
# UI
# ==========================================
st.markdown("<h1>🏦 OPTIONS DASHBOARD 🏦</h1>", unsafe_allow_html=True)
import pytz

ist = pytz.timezone("Asia/Kolkata")
current_time = datetime.now(ist)

st.markdown(f"### ⏰ Time (IST): {current_time.strftime('%H:%M:%S')}")

# Updated Dropdown
symbol = st.selectbox("Select Instrument", ["SENSEX", "NIFTY", "BANKNIFTY", "FINNIFTY", "NIFTY FUT"])

token = get_token(symbol)

df5 = apply_indicators(get_data(token, "5minute"))
df15 = apply_indicators(get_data(token, "15minute"))

if df5.empty:
    st.error("No data")
    st.stop()

price = df5["close"].iloc[-1]

if symbol != "NIFTY FUT":
    option_df = get_option_chain(symbol, price)
else:
    option_df = pd.DataFrame()

signal = advanced_signal(df5, df15, option_df)
smart_flow = smart_money_flow(option_df)

# ✅ ONLY ADD
support, resistance = calculate_support_resistance(df5)
oi_support, oi_resistance = calculate_oi_levels(option_df)

# ==========================================
# CAPITAL
# ==========================================
capital = 12000

# Updated Maps for Lot Size and Strike Steps
lot_map = {"SENSEX":10, "NIFTY":50, "BANKNIFTY":15, "FINNIFTY":40, "NIFTY FUT":50}
step_map = {"SENSEX":100, "NIFTY":50, "BANKNIFTY":100, "FINNIFTY":50, "NIFTY FUT":50}

lot = lot_map[symbol]
step = step_map[symbol]

atm = round(price/step)*step
itm = atm-step
otm = atm+step

def get_premium(strike, typ):
    if option_df.empty or "strike" not in option_df.columns:
        return 0

    r = option_df[
        (option_df["strike"] == strike) & (option_df["type"] == typ)
    ]
    return r.iloc[0]["ltp"] if not r.empty else 0

if signal=="CALL":
    atm_p = get_premium(atm,"CE")
else:
    atm_p = get_premium(atm,"PE")

def lots(p): return int(capital//(p*lot)) if p else 0

# ==========================================
# METRICS
# ==========================================
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Price",round(price,2))
c2.metric("RSI",round(df5["RSI"].iloc[-1],2))
c3.metric("Trend","UP" if df5["EMA20"].iloc[-1]>df5["EMA50"].iloc[-1] else "DOWN")
c4.metric("ADX",round(df5["ADX"].iloc[-1],2))
c5.metric("Signal",signal)

st.markdown("### 🧠 Smart Money / FII Flow")
st.info(smart_flow)

# ==========================================
# TRADE OUTPUT
# ==========================================
st.subheader("🎯 Trade Suggestion")

if signal=="CALL":
    st.success(f"CALL → ATM {atm} | Lots: {lots(atm_p)}")
elif signal=="PUT":
    st.error(f"PUT → ATM {atm} | Lots: {lots(atm_p)}")
else:
    st.warning("WAIT - No clear signal")

# ✅ ONLY ADD
st.markdown(f"""
### 📊 Key Levels
🟢 Price Support: {support}
🔴 Price Resistance: {resistance}

🟢 OI Support: {oi_support}
🔴 OI Resistance: {oi_resistance}
""")

# ==========================================
# 🔥 HEATMAP (LIGHT COLOR + BOLD LABELS)
# ==========================================
st.subheader("🔥 Open Interest Heatmap")

if option_df.empty or "strike" not in option_df.columns:
    st.info("No option data available for heatmap")
else:
    heatmap_chart = alt.Chart(option_df).mark_rect().encode(
        x=alt.X(
            "strike:O",
            title="Strike",
            axis=alt.Axis(labelFontWeight="bold")  # ✅ Bold Strike
        ),
        y=alt.Y(
            "type:N",
            title="Type",
            axis=alt.Axis(labelFontWeight="bold")  # ✅ Bold Type
        ),
        color=alt.Color(
            "oi:Q",
            scale=alt.Scale(scheme="lightorange"),  # ✅ Softer light color
            title="Open Interest",
            legend=alt.Legend(titleFontWeight="bold")  # ✅ Bold legend title
        ),
        tooltip=["strike", "type", "oi"]
    ).properties(height=320)

    st.altair_chart(heatmap_chart, use_container_width=True)

# ==========================================
# CHART
# ==========================================
st.subheader("📈 Price Chart")

chart_data = df5.reset_index()

chart = alt.Chart(chart_data).transform_fold(
    ["close", "EMA20", "EMA50", "VWAP"],
    as_=["Metric", "Value"]
).mark_line().encode(
    x="date:T",
    y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
    color="Metric:N"
).properties(height=400)

st.altair_chart(chart, use_container_width=True)

# ==========================================
# OPTION CHAIN
# ==========================================
st.subheader("📊 Option Chain")
st.dataframe(option_df, use_container_width=True)
