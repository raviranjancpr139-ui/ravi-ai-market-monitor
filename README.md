# Ravi AI Multi-Market Monitor — Free Starter

An educational market-condition dashboard designed to open in a browser on an Android tablet.

## What it does
- Reads market data through `yfinance` (Yahoo Finance).
- Calculates EMA 9, EMA 21, RSI, MACD and intraday VWAP.
- Classifies market conditions as bullish momentum, bearish momentum, or mixed/sideways.
- Can send a Telegram message when a symbol changes into bullish or bearish momentum.
- Does **not** place orders or connect to a broker.

## Important data limitations
- `yfinance` is an unofficial interface to Yahoo Finance, not an exchange-grade or guaranteed real-time feed.
- Intraday 5-minute data may be delayed, missing, rate-limited, or unavailable for some symbols.
- The commodity tickers are global futures proxies (US contracts), not Indian MCX contracts.
- Currency and crypto symbols may have different session and timestamp conventions.
- Use for education and observation only, not for financial decisions or trade execution.

## Run locally
1. Install Python 3.10 or later.
2. In a terminal, run:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
3. Open the local URL shown by Streamlit.

## Telegram setup
1. In Telegram, open the official `@BotFather`, create a bot, and copy its token.
2. Open your new bot and send `/start`.
3. Obtain your own chat ID using a trusted Telegram bot/API method. Keep it private.
4. For local testing, create `.streamlit/secrets.toml`:
   ```toml
   TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
   TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
   ```
5. Restart Streamlit. The dashboard will show whether Telegram credentials are detected.

Never publish your bot token or commit `secrets.toml` to GitHub.

## Deploy for browser access on Android
A simple path is Streamlit Community Cloud:
1. Create a private GitHub repository and upload `app.py`, `requirements.txt`, and this README.
2. Connect the repository to Streamlit Community Cloud.
3. Set `app.py` as the app file.
4. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the app's Secrets settings.
5. Deploy and open the resulting app URL in Chrome on your Android tablet.

Free hosting may sleep, restart, or have resource limits. Telegram alerts are only generated while the app is running and successfully refreshing. This is not an always-on guaranteed alert service.

## Symbols
The app starts with a sample watchlist. Symbols may need adjustment depending on data availability:
- NIFTY 50: `^NSEI`
- BANK NIFTY: `^NSEBANK`
- Indian shares: `.NS` tickers
- Gold/Silver/WTI Crude/Natural Gas: `GC=F`, `SI=F`, `CL=F`, `NG=F`
- NASDAQ/S&P 500/Dow: `^IXIC`, `^GSPC`, `^DJI`
- Bitcoin/Ethereum: `BTC-USD`, `ETH-USD`

## Alert behaviour
Alerts are sent only when the calculated state changes into bullish or bearish momentum. A small local SQLite file remembers the last state. On free cloud hosting, local files may be reset when an app restarts, so occasional repeat alerts are possible.
