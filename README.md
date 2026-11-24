# Telegram alerts for PDH, PDL, PWH, PWL and previous 4H levels

This repository checks 21 instruments and sends a Telegram alert when a completed 5-minute candle touches one of six levels:

- Previous UTC day high/low (PDH/PDL)
- Previous UTC Monday-to-Monday week high/low (PWH/PWL)
- Previous completed UTC-aligned 4-hour block high/low (P4H HIGH/P4H LOW)

A touch means `candle low <= level <= candle high`. Alerts are price-level touches only; this does not run the entry, stop, or target rules from a trading strategy. It sends one alert per level/reference period, then suppresses repeated touches of that same level until the reference period changes. The scanner only uses closed candles and ignores touches older than 20 minutes.

## Data source

This uses the same no-Twelve-Data approach as the supplied JP-Alerts repository: public OKX OHLCV through CCXT for BTC and ETH, and Yahoo Finance candles through yfinance for forex and commodity futures. No paid market-data API key is configured. The source provides exchange/futures prices that can differ from your broker's CFDs or spot chart. In particular, `GC=F`, `SI=F`, and `CL=F` are gold, silver, and WTI futures proxies. Confirm the symbols and prices suit your chart before relying on the alerts. Yahoo Finance availability and intraday history are not guaranteed; check Actions logs if a symbol reports an error or empty data.

## Instruments

XAUUSD, XAGUSD, BTC, ETH, USOIL, EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCHF, EURCHF, GBPCHF, USDJPY, EURJPY, GBPJPY, AUDJPY, GBPCAD, AUDCAD, EURAUD, EURGBP, CHFJPY.

Mappings are in `config.yaml`. Change the provider ticker there if your chosen market source uses a different symbol. Metals and oil default to futures proxies; BTC/ETH use OKX USDT pairs.

## Telegram and GitHub Actions setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather), start a chat with it, and obtain the chat ID.
2. Push this repository to GitHub. The workflow runs on a five-minute cron and can also be started manually from the Actions tab. GitHub may delay scheduled runs during high load.
3. In **Settings → Secrets and variables → Actions**, add repository secrets:
   - `TELEGRAM_TOKEN`: the bot token from BotFather
   - `TELEGRAM_CHAT_ID`: your private chat ID
4. In **Settings → Actions → General → Workflow permissions**, allow read and write access so the workflow can commit `state.json` and prevent duplicate alerts.
5. Enable Actions. To verify Telegram delivery, open **Actions → Market level Telegram alerts → Run workflow**, select **test_telegram**, and run it. It sends one test message without scanning markets. To get a combined message like the JP Alerts screenshot, select **scan_summary** and run the workflow; it sends one list of all symbols, latest prices, and any level touch in the latest candle. For normal automatic alerts, leave both options unchecked and run the workflow. Inspect the run log for symbols that did not return candles.

After the workflow has run at least once, send `/start` to the bot for a short help reply, or `/scan` for a current multi-market scan summary. Telegram commands are checked during the existing five-minute workflow schedule, so a command may take several minutes to receive a reply; GitHub can also delay scheduled runs. Command polling is restricted to `TELEGRAM_CHAT_ID`. Normal level-touch alerts continue to be sent automatically.

The workflow checks all symbols serially. It keeps alert deduplication and last-checked candle timestamps in `state.json`; the workflow commits changes after each run. Keep this file in the repository. If you clear it, the next run starts fresh.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
python main.py
```

The local process performs one scan. Schedule it externally if you want repeated local checks. Never commit bot tokens or chat credentials; keep them in GitHub Actions secrets or environment variables.
