import os
import requests

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID")
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             data={"chat_id": chat, "text": text}, timeout=20)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok:
        description = payload.get("description") or response.text or response.reason
        raise RuntimeError(f"Telegram API returned HTTP {response.status_code}: {description}")
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description", "Telegram send failed"))
