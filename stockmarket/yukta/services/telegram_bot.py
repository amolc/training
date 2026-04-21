import json
import os
from pathlib import Path
from typing import Optional

import requests

BOT_TOKEN = os.getenv(
    "YUKTA_TELEGRAM_BOT_TOKEN",
    "8443977617:AAFvK6B4WnDqCfxivhriqKi88ouk7E3y6Uc",
)
CHAT_ID = os.getenv("YUKTA_TELEGRAM_CHAT_ID", "8082694842")
TELEGRAM_ALERTS_ENABLED = os.getenv("YUKTA_TELEGRAM_ALERTS_ENABLED", "true").lower() == "true"

ALERT_STATE_FILE = Path(__file__).resolve().parent / ".telegram_alert_state.json"


def _build_alert_key(symbol: str, signal: str, candle_time: str) -> str:
    return f"{symbol}|{signal}|{candle_time}"


def _load_last_alert_key() -> Optional[str]:
    if not ALERT_STATE_FILE.exists():
        return None
    try:
        payload = json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload.get("last_alert_key")


def _save_last_alert_key(alert_key: str) -> None:
    try:
        ALERT_STATE_FILE.write_text(
            json.dumps({"last_alert_key": alert_key}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # Do not crash strategy if state file cannot be written.
        pass


def is_new_signal_alert(symbol: str, signal: str, candle_time: str) -> bool:
    alert_key = _build_alert_key(symbol=symbol, signal=signal, candle_time=candle_time)
    last_alert_key = _load_last_alert_key()
    if alert_key == last_alert_key:
        return False
    _save_last_alert_key(alert_key)
    return True


def build_signal_message(symbol: str, signal: str, price: float, candle_time: str) -> str:
    return (
        "🚨 SIGNAL ALERT\n"
        f"Symbol: {symbol}\n"
        f"Signal: {signal}\n"
        f"Price: {price}\n"
        f"Time: {candle_time}"
    )


def send_telegram_message(message: str) -> bool:
    if not TELEGRAM_ALERTS_ENABLED:
        print("Telegram alerts disabled.")
        return False
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials are missing.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Telegram send failed: {exc}")
        return False
    return True
