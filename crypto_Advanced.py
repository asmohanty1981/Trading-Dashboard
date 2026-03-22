# ==========================================
# 🚀 PRO CRYPTO DASHBOARD (BTC + ETH)
# ==========================================

import streamlit as st
import pandas as pd
from binance.client import Client
import ta
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from dotenv import load_dotenv
import os

# ================================
# ENV
# ================================
load_dotenv()
client = Client(st.secrets["BINANCE_API_KEY"], st.secrets["BINANCE_API_SECRET"])
client.API_URL = 'https://api1.binance.com/api' # Try api1, api2, or api3

SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}

# ================================
# 🔥 TIMEFRAME SELECTOR (ADDED)
# ================================
timeframe = st.sidebar.selectbox(
    "⏱ Timeframe",
    ["4h", "1h", "15m"]
)

interval_map = {
    "4h": Client.KLINE_INTERVAL_4HOUR,
	"1h": Client.KLINE_INTERVAL_1HOUR,
    "15m": Client.KLINE_INTERVAL_15MINUTE
}

INTERVAL = interval_map[timeframe]
LIMIT = 300

# ================================
# AUTO REFRESH
# ================================
st_autorefresh(interval=60000, key="refresh")

st.set_page_config(layout="wide")
st.title("🚀 PRO CRYPTO DASHBOARD")

# ================================
# DATA
# ================================
def get_data(symbol):
    klines = client.get_klines(symbol=symbol, interval=INTERVAL, limit=LIMIT)
    df = pd.DataFrame(klines, columns=[
        "time","open","high","low","close","volume",
        "ct","qav","nt","tb","tq","ignore"
    ])
    df["time"] = pd.to_datetime(df["time"], unit='ms')
    df.set_index("time", inplace=True)

    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)

    return df

# ================================
# INDICATORS
# ================================
def add_indicators(df):

    df["EMA20"] = ta.trend.ema_indicator(df["close"], 20)
    df["EMA50"] = ta.trend.ema_indicator(df["close"], 50)
    df["EMA200"] = ta.trend.ema_indicator(df["close"], 200)

    df["RSI"] = ta.momentum.rsi(df["close"], 14)

    macd = ta.trend.macd(df["close"])
    df["MACD"] = macd
    df["MACD_signal"] = ta.trend.macd_signal(df["close"])

    bb = ta.volatility.BollingerBands(df["close"])
    df["bb_high"] = bb.bollinger_hband()
    df["bb_low"] = bb.bollinger_lband()

    df["VWAP"] = (df["volume"] * (df["high"]+df["low"]+df["close"])/3).cumsum()/df["volume"].cumsum()

    df["vol_spike"] = df["volume"] > df["volume"].rolling(20).mean() * 2

    return df

# ================================
# SIGNAL ENGINE
# ================================
def get_signal(df):
    latest = df.iloc[-1]

    if latest["EMA20"] > latest["EMA50"] > latest["EMA200"] and latest["RSI"] > 55:
        return "🟢 STRONG BUY"
    elif latest["EMA20"] < latest["EMA50"] < latest["EMA200"] and latest["RSI"] < 45:
        return "🔴 STRONG SELL"
    elif latest["RSI"] > 60:
        return "🟢 BUY"
    elif latest["RSI"] < 40:
        return "🔴 SELL"
    else:
        return "⚪ SIDEWAYS"

# ================================
# TRADE SUGGESTION
# ================================
def trade_levels(df):
    latest = df.iloc[-1]
    price = latest["close"]

    if "BUY" in get_signal(df):
        entry = price
        sl = price * 0.98
        target = price * 1.03
        setup = "🟢 BULLISH"
    else:
        entry = price
        sl = price * 1.02
        target = price * 0.97
        setup = "🔴 BEARISH"

    return setup, entry, sl, target

# ================================
# FUTURES DATA
# ================================
def get_futures(symbol):
    oi = client.futures_open_interest(symbol=symbol)["openInterest"]
    fr = client.futures_funding_rate(symbol=symbol)[-1]["fundingRate"]
    return float(oi), float(fr)

# ================================
# CHART
# ================================
def plot_chart(df, name):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['open'], high=df['high'],
        low=df['low'], close=df['close']
    ))

    fig.add_trace(go.Scatter(x=df.index, y=df["EMA20"], name="EMA20"))
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], name="EMA50"))
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA200"], name="EMA200"))
    fig.add_trace(go.Scatter(x=df.index, y=df["VWAP"], name="VWAP"))

    fig.add_trace(go.Scatter(x=df.index, y=df["bb_high"], name="BB High"))
    fig.add_trace(go.Scatter(x=df.index, y=df["bb_low"], name="BB Low"))

    fig.update_layout(height=500, title=name)

    st.plotly_chart(fig, use_container_width=True)

# ================================
# MAIN UI
# ================================
cols = st.columns(2)

for i, (name, symbol) in enumerate(SYMBOLS.items()):

    df = get_data(symbol)
    df = add_indicators(df)

    price = df["close"].iloc[-1]
    signal = get_signal(df)
    setup, entry, sl, target = trade_levels(df)

    oi, fr = get_futures(symbol)

    col = cols[i]

    with col:
        st.subheader(f"📊 {name}")

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Price", f"{price:.2f}")
        c2.metric("📡 Signal", signal)
        c3.metric("📊 RSI", f"{df['RSI'].iloc[-1]:.2f}")

        st.write(f"📈 OI: {oi}")
        st.write(f"💸 Funding Rate: {fr:.5f}")

        plot_chart(df, name)

        st.markdown("### 🎯 Trade Suggestion")
        st.success(f"{setup}")
        st.write(f"👉 Entry: {entry:.2f}")
        st.write(f"🛑 SL: {sl:.2f}")
        st.write(f"🎯 Target: {target:.2f}")

        if df["vol_spike"].iloc[-1]:
            st.warning("⚡ Volume Spike Detected!")

        st.markdown("---")
