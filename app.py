import os
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except Exception:
    AUTOREFRESH_AVAILABLE = False

st.set_page_config(page_title="Ravi AI Market Monitor", page_icon="📊", layout="wide")

WATCHLIST = {
    "Indian Indices": {
        "NIFTY 50": "^NSEI",
        "BANK NIFTY": "^NSEBANK",
    },
    "Indian Stocks (examples)": {
        "RELIANCE": "RELIANCE.NS",
        "HDFC BANK": "HDFCBANK.NS",
        "ICICI BANK": "ICICIBANK.NS",
        "INFOSYS": "INFY.NS",
        "TCS": "TCS.NS",
    },
    "Global Commodity Proxies": {
        "Gold futures (US)": "GC=F",
        "Silver futures (US)": "SI=F",
        "Crude Oil futures (WTI)": "CL=F",
        "Natural Gas futures (US)": "NG=F",
    },
    "Global Indices": {
        "NASDAQ Composite": "^IXIC",
        "S&P 500": "^GSPC",
        "Dow Jones": "^DJI",
    },
    "FX Proxies": {
        "USD/INR": "INR=X",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "JPY=X",
    },
    "Crypto": {
        "Bitcoin": "BTC-USD",
        "Ethereum": "ETH-USD",
    },
}

DB_PATH = os.environ.get("RAVI_DB_PATH", "ravi_monitor_state.sqlite3")


def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.environ.get(name, default)


def fetch_data(symbol, period="5d", interval="5m"):
    try:
        df = yf.Ticker(symbol).history(
            period=period, interval=interval, auto_adjust=False, prepost=False
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns=str.title)
        required = {"Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(df.columns):
            return pd.DataFrame()
        df = df.dropna(subset=["Close"])
        return df
    except Exception:
        return pd.DataFrame()


def add_indicators(df):
    out = df.copy()
    close = out["Close"]
    out["EMA 9"] = close.ewm(span=9, adjust=False).mean()
    out["EMA 21"] = close.ewm(span=21, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["RSI"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["MACD"] = ema12 - ema26
    out["MACD Signal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["MACD Hist"] = out["MACD"] - out["MACD Signal"]

    # Intraday VWAP resets by calendar date in the data's exchange timezone.
    typical = (out["High"] + out["Low"] + close) / 3
    vol = out["Volume"].fillna(0)
    if isinstance(out.index, pd.DatetimeIndex):
        date_key = pd.Series(out.index.date, index=out.index)
        cum_pv = (typical * vol).groupby(date_key).cumsum()
        cum_vol = vol.groupby(date_key).cumsum().replace(0, np.nan)
        out["VWAP"] = cum_pv / cum_vol
    else:
        out["VWAP"] = np.nan
    return out


def classify(last):
    checks = [
        pd.notna(last.get("EMA 9")),
        pd.notna(last.get("EMA 21")),
        pd.notna(last.get("RSI")),
    ]
    if not all(checks):
        return "INSUFFICIENT DATA"
    vwap = last.get("VWAP")
    vwap_ok_bull = pd.isna(vwap) or last["Close"] > vwap
    vwap_ok_bear = pd.isna(vwap) or last["Close"] < vwap
    bull = (
        last["Close"] > last["EMA 9"] > last["EMA 21"]
        and last["RSI"] >= 55
        and last["MACD Hist"] > 0
        and vwap_ok_bull
    )
    bear = (
        last["Close"] < last["EMA 9"] < last["EMA 21"]
        and last["RSI"] <= 45
        and last["MACD Hist"] < 0
        and vwap_ok_bear
    )
    if bull:
        return "BULLISH MOMENTUM"
    if bear:
        return "BEARISH MOMENTUM"
    return "MIXED / SIDEWAYS"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS last_alert (
                symbol TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()


def should_send_alert(symbol, state):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT state FROM last_alert WHERE symbol = ?", (symbol,)
        ).fetchone()
        if row and row[0] == state:
            return False
        conn.execute(
            """INSERT INTO last_alert(symbol, state, updated_at)
               VALUES(?, ?, ?)
               ON CONFLICT(symbol) DO UPDATE SET
               state=excluded.state, updated_at=excluded.updated_at""",
            (symbol, state, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    return True


def send_telegram(message):
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "Telegram not configured"
    try:
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=15,
        )
        if response.ok:
            return True, "Sent"
        return False, f"Telegram API error: HTTP {response.status_code}"
    except Exception as exc:
        return False, f"Telegram error: {exc}"


def money(value):
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "—"


st.title("📊 Ravi AI Multi-Market Monitor")
st.caption("Educational market-condition monitoring • No order execution • Not investment advice")

with st.sidebar:
    st.header("Monitor settings")
    interval_label = st.selectbox("Chart interval", ["5 minutes", "15 minutes", "1 hour"], index=0)
    interval_map = {"5 minutes": "5m", "15 minutes": "15m", "1 hour": "60m"}
    interval = interval_map[interval_label]
    refresh_seconds = st.selectbox("Refresh frequency", [60, 180, 300, 600], index=2)
    selected_groups = st.multiselect(
        "Market groups",
        list(WATCHLIST.keys()),
        default=["Indian Indices", "Global Commodity Proxies"],
    )
    telegram_enabled = st.checkbox("Send Telegram alerts when market state changes", value=True)
    st.caption("Yahoo Finance data may be delayed, incomplete or unavailable. Do not use it as an execution feed.")

if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=refresh_seconds * 1000, key="ravi_refresh")
else:
    st.info("Auto-refresh package is unavailable. Use the Refresh button.")
if st.button("🔄 Refresh now"):
    st.rerun()

init_db()

instruments = {}
for group in selected_groups:
    instruments.update(WATCHLIST[group])

if not instruments:
    st.warning("Select at least one market group in the sidebar.")
    st.stop()

rows = []
data_by_name = {}
progress = st.progress(0, text="Fetching market data…")
for idx, (name, symbol) in enumerate(instruments.items(), start=1):
    raw = fetch_data(symbol, period="5d", interval=interval)
    if not raw.empty:
        enriched = add_indicators(raw)
        last = enriched.iloc[-1]
        state = classify(last)
        data_by_name[name] = (symbol, enriched)
        rows.append({
            "Instrument": name,
            "Symbol": symbol,
            "Market state": state,
            "Last price": money(last["Close"]),
            "RSI": money(last["RSI"]),
            "EMA 9": money(last["EMA 9"]),
            "EMA 21": money(last["EMA 21"]),
            "VWAP": money(last["VWAP"]),
            "Last candle": str(enriched.index[-1]),
        })
        if telegram_enabled and state in ("BULLISH MOMENTUM", "BEARISH MOMENTUM"):
            if should_send_alert(symbol, state):
                msg = (
                    "📊 RAVI AI MARKET MONITOR\n"
                    "Educational observation — not a trade instruction\n\n"
                    f"Instrument: {name} ({symbol})\n"
                    f"Interval: {interval_label}\n"
                    f"Market state: {state}\n"
                    f"Last price: {money(last['Close'])}\n"
                    f"RSI: {money(last['RSI'])}\n"
                    f"EMA 9: {money(last['EMA 9'])}\n"
                    f"EMA 21: {money(last['EMA 21'])}\n"
                    f"VWAP: {money(last['VWAP'])}\n"
                    f"Data candle: {enriched.index[-1]}\n"
                )
                send_telegram(msg)
    else:
        rows.append({
            "Instrument": name,
            "Symbol": symbol,
            "Market state": "DATA UNAVAILABLE",
            "Last price": "—",
            "RSI": "—",
            "EMA 9": "—",
            "EMA 21": "—",
            "VWAP": "—",
            "Last candle": "—",
        })
    progress.progress(idx / len(instruments), text=f"Checked {name}")
progress.empty()

if rows:
    summary = pd.DataFrame(rows)
    st.subheader("Market overview")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.subheader("Instrument detail")
    available_names = list(data_by_name.keys())
    if available_names:
        chosen = st.selectbox("Choose an instrument", available_names)
        symbol, chart_df = data_by_name[chosen]
        last = chart_df.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Last price", money(last["Close"]))
        c2.metric("Market state", classify(last))
        c3.metric("RSI", money(last["RSI"]))
        c4.metric("VWAP", money(last["VWAP"]))
        chart = chart_df[["Close", "EMA 9", "EMA 21", "VWAP"]].tail(120)
        st.line_chart(chart, height=350)
        st.caption(f"Data source: Yahoo Finance via yfinance • Symbol: {symbol} • Last returned candle: {chart_df.index[-1]}")
    else:
        st.warning("No selected instruments currently returned data.")
else:
    st.warning("No market data returned.")

st.divider()
st.subheader("Telegram setup status")
if get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"):
    st.success("Telegram credentials detected. Alerts are sent only when a symbol changes into a bullish or bearish momentum state.")
else:
    st.info("Telegram is not configured yet. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to Streamlit secrets to enable alerts.")

st.caption(
    "Important: This is an educational monitoring dashboard, not a broker terminal. "
    "It does not place, modify or close orders. Free data can be delayed and is not guaranteed. "
    "Global futures symbols are proxies and are not the same as Indian MCX contracts."
)
