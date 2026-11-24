import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import requests
import yaml

from alerts import send_telegram
from data import get_data
from levels import levels_at

STATE_PATH = Path("state.json")
FRESH_MINUTES = 20

def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"symbols": {}}

def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))

def poll_telegram_commands(state, cfg):
    """Answer /start and /scan messages addressed to the configured chat."""
    token = os.getenv("TELEGRAM_TOKEN")
    expected_chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not expected_chat:
        return

    offset = state.get("telegram_update_offset")
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
    if offset is not None:
        params["offset"] = int(offset)
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params=params,
            timeout=20,
        )
        payload = response.json()
        if not response.ok or not payload.get("ok"):
            raise RuntimeError(payload.get("description", f"HTTP {response.status_code}"))

        for update in payload.get("result", []):
            state["telegram_update_offset"] = int(update["update_id"]) + 1
            message = update.get("message", {})
            chat = message.get("chat", {})
            if str(chat.get("id")) != str(expected_chat):
                continue
            text = (message.get("text") or "").strip()
            if not text:
                continue
            command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
            if command == "/start":
                send_telegram(
                    "👋 Market Level Alerts is connected.\n"
                    "Send /scan for current prices and level status.\n"
                    "Touch alerts are checked automatically about every 5 minutes."
                )
                logging.info("Answered Telegram /start")
            elif command == "/scan":
                try:
                    send_telegram(scan_summary(cfg))
                    logging.info("Answered Telegram /scan")
                except Exception as exc:
                    logging.exception("Telegram /scan failed")
                    send_telegram(f"⚠️ Scan could not be completed: {str(exc)[:300]}")
    except Exception:
        # A temporary Telegram polling issue should not stop scheduled market alerts.
        logging.exception("Could not poll Telegram commands")

def check_symbol(sym, state, now=None, data_fn=get_data, notify=send_telegram):
    now = now or pd.Timestamp.now(tz="UTC")
    name = sym["name"]
    item = state["symbols"].setdefault(name, {"last_candle": None, "sent": []})
    hourly, candles = data_fn(sym, now)
    if candles.empty:
        logging.warning("%s: no completed touch candles", name)
        return

    last_ts = item.get("last_candle")
    if last_ts is None:
        new = candles.tail(1)
    else:
        last = pd.Timestamp(last_ts)
        last = last.tz_localize("UTC") if last.tzinfo is None else last.tz_convert("UTC")
        new = candles[candles.index > last]

    sent = set(item.get("sent", []))
    for ts, candle in new.iterrows():
        if now - ts > pd.Timedelta(minutes=FRESH_MINUTES):
            continue
        for level_name, level_price, period in levels_at(hourly, ts):
            if float(candle["low"]) <= level_price <= float(candle["high"]):
                key = f"{level_name}|{period}"
                if key in sent:
                    continue
                candle_minutes = int(sym.get("chart_minutes", 5))
                candle_end = ts + pd.Timedelta(minutes=candle_minutes)
                detected_at = pd.Timestamp.now(tz="UTC").tz_convert("Asia/Kolkata")
                text = (
                    f"🔔 LEVEL TOUCH — {name}\n"
                    f"Level: {level_name} at {level_price:.10g}\n"
                    f"5m candle range: {float(candle['low']):.10g} – {float(candle['high']):.10g}\n"
                    f"Touch candle (IST): {ts.tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %H:%M')}–{candle_end.tz_convert('Asia/Kolkata').strftime('%H:%M')}\n"
                    f"Alert detected (IST): {detected_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    "Exact tick time is unavailable from 5-minute candle data.\n"
                    f"Reference period: {period}"
                )
                notify(text)
                sent.add(key)
                item["sent"] = sorted(sent)[-300:]
                logging.info("Alert sent: %s %s %.10g", name, level_name, level_price)

    item["last_candle"] = candles.index[-1].isoformat()
    item["sent"] = sorted(sent)[-300:]

PRICE_DECIMALS = {
    "XAUUSD": 1, "XAGUSD": 3, "BTC": 2, "ETH": 2, "USOIL": 2,
    "USDJPY": 3, "EURJPY": 3, "GBPJPY": 3, "AUDJPY": 3, "CHFJPY": 3,
}

def scan_summary(cfg, now=None, data_fn=get_data):
    """Build one Telegram scan-results message for the configured markets."""
    now = now or pd.Timestamp.now(tz="UTC")
    now_ist = now.tz_convert("Asia/Kolkata")
    lines = [f"📊 Scan results — {now_ist.strftime('%Y-%m-%d %H:%M IST')}"]
    available = 0
    for sym in cfg["symbols"]:
        name = sym["name"]
        try:
            hourly, candles = data_fn(sym, now)
            if candles.empty:
                lines.append(f"{name}: unavailable — no closed candle")
                continue
            available += 1
            ts = candles.index[-1]
            candle = candles.iloc[-1]
            price = float(candle["close"])
            decimals = PRICE_DECIMALS.get(name, 5)
            hits = [label for label, level, _period in levels_at(hourly, ts)
                    if float(candle["low"]) <= level <= float(candle["high"])]
            if now - ts > pd.Timedelta(minutes=FRESH_MINUTES):
                status = f"stale quote ({ts.strftime('%H:%M UTC')})"
            elif hits:
                candle_end = ts + pd.Timedelta(minutes=int(sym.get("chart_minutes", 5)))
                candle_window = (
                    f"{ts.tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %H:%M')}–"
                    f"{candle_end.tz_convert('Asia/Kolkata').strftime('%H:%M IST')}"
                )
                status = ", ".join(f"{label} touched" for label in hits)
                status += f" (candle {candle_window})"
            else:
                status = "no new level touch"
            lines.append(f"{name}: {price:.{decimals}f} — {status}")
        except Exception as exc:
            logging.exception("Scan summary failed for %s", name)
            lines.append(f"{name}: unavailable — {str(exc)[:70]}")
    if available == 0:
        raise RuntimeError("No market data was available for the scan summary")
    return "\n".join(lines)

def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    if not os.getenv("TELEGRAM_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
        raise RuntimeError("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in GitHub Actions secrets")
    if "--test-telegram" in sys.argv:
        send_telegram("✅ Telegram connection test succeeded. The market alert bot can reach this chat.")
        logging.info("Telegram test message sent successfully")
        return
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    state = load_state()
    poll_telegram_commands(state, cfg)
    if "--scan-summary" in sys.argv:
        send_telegram(scan_summary(cfg))
        logging.info("Telegram scan summary sent")
        save_state(state)
        return
    failures = 0
    for sym in cfg["symbols"]:
        try:
            check_symbol(sym, state)
        except Exception:
            failures += 1
            logging.exception("Failed checking %s", sym["name"])
        finally:
            save_state(state)
    logging.info("Checked %d instruments (%d failed)", len(cfg["symbols"]), failures)
    if failures == len(cfg["symbols"]):
        raise RuntimeError("All symbols failed; inspect provider availability and workflow logs")

if __name__ == "__main__":
    main()
