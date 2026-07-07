import asyncio
import os
import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

import requests
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_STRING = os.getenv("TG_SESSION_STRING", "").strip()
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
PAYMENT_SECRET = os.getenv("PAYMENT_SECRET", "")
WEBHOOK_PATH = "/api/payments/cardxabar"

_PLUS = re.compile(r"[\u2795\uFF0B+]")
_NUMBER = re.compile(r"[0-9][0-9\s\u00a0.,]*[0-9]|[0-9]")

def parse_amount_to_tiyin(text):
    line = None
    for l in text.splitlines():
        if _PLUS.search(l) and any(c.isdigit() for c in l):
            line = l
            break
    if line is None:
        return None
    m = _NUMBER.search(line)
    if not m:
        return None
    token = m.group(0).replace(" ", "").replace("\u00a0", "")
    if "," in token and "." in token:
        token = token.replace(",", "")
    elif "," in token:
        token = token.replace(",", ".")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    tiyin = int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))
    return tiyin if tiyin > 0 else None

def _post_webhook(tiyin, raw):
    resp = requests.post(
        f"{BACKEND_URL}{WEBHOOK_PATH}",
        json={"amountTiyin": tiyin, "raw": raw},
        headers={"X-Payment-Secret": PAYMENT_SECRET, "Content-Type": "application/json"},
        timeout=15,
    )
    return resp.status_code, resp.text

async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"[userbot] logged in as @{me.username or ''} (id={me.id})")
    try:
        await client.get_dialogs()
    except Exception as exc:
        print(f"[userbot] get_dialogs warning: {exc}")
    print("[userbot] DEBUG MODE - printing EVERY incoming message")

    @client.on(events.NewMessage())
    async def handler(event):
        try:
            sender = await event.get_sender()
        except Exception:
            sender = None
        uname = getattr(sender, "username", None)
        sid = getattr(sender, "id", None)
        text = event.raw_text or ""
        print(f"[msg] chat_id={event.chat_id} sender_id={sid} username=@{uname} text={text[:120]!r}")
        tiyin = parse_amount_to_tiyin(text)
        if tiyin and _PLUS.search(text):
            print(f"[userbot] credit detected: {tiyin} tiyin -> posting")
            try:
                status, resp = await asyncio.to_thread(_post_webhook, tiyin, text)
                print(f"[userbot] webhook {status}: {resp[:200]}")
            except Exception as exc:
                print(f"[userbot] webhook error: {exc}")

    print("[userbot] ready (DEBUG)")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
