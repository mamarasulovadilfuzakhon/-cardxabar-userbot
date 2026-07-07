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
SESSION_NAME = os.getenv("TG_SESSION", "cardxabar_userbot")
SESSION_STRING = os.getenv("TG_SESSION_STRING", "").strip()
CARDXABAR_SOURCE = os.getenv("CARDXABAR_SOURCE", "").strip()
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
PAYMENT_SECRET = os.getenv("PAYMENT_SECRET", "")
CARD_LAST4 = os.getenv("CARD_LAST4", "").strip()
WEBHOOK_PATH = "/api/payments/cardxabar"

def _sources():
    out = []
    for part in CARDXABAR_SOURCE.split(","):
        p = part.strip().lstrip("@")
        if not p:
            continue
        out.append(int(p) if p.lstrip("-").isdigit() else p)
    return out

_CREDIT_LINE = re.compile(r"\u2795")
_NUMBER = re.compile(r"[0-9][0-9\s.,]*[0-9]|[0-9]")

def parse_amount_to_tiyin(text):
    credit_line = None
    for line in text.splitlines():
        if _CREDIT_LINE.search(line):
            credit_line = line
            break
    if credit_line is None:
        return None
    m = _NUMBER.search(credit_line)
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
    url = f"{BACKEND_URL}{WEBHOOK_PATH}"
    resp = requests.post(
        url,
        json={"amountTiyin": tiyin, "raw": raw},
        headers={"X-Payment-Secret": PAYMENT_SECRET, "Content-Type": "application/json"},
        timeout=15,
    )
    return resp.status_code, resp.text

async def notify_backend(tiyin, raw):
    try:
        status, text = await asyncio.to_thread(_post_webhook, tiyin, raw)
    except Exception as exc:
        print(f"[userbot] webhook error: {exc}")
        return
    if status == 200 and '"matched":true' in text.replace(" ", ""):
        print(f"[userbot] matched & activated: {tiyin} tiyin")
    elif status == 200:
        print(f"[userbot] no matching order for {tiyin} tiyin (ignored)")
    else:
        print(f"[userbot] webhook returned {status}: {text}")

def _build_client():
    if SESSION_STRING:
        return TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def main():
    client = _build_client()
    sources = _sources()

    @client.on(events.NewMessage(chats=sources))
    async def handler(event):
        text = event.raw_text or ""
        if "\u2795" not in text:
            return
        if CARD_LAST4 and CARD_LAST4 not in text:
            return
        tiyin = parse_amount_to_tiyin(text)
        if not tiyin:
            print("[userbot] could not parse amount; skipping")
            return
        print(f"[userbot] incoming credit detected: {tiyin} tiyin")
        await notify_backend(tiyin, text)

    await client.start()
    me = await client.get_me()
    who = f"@{me.username}" if me.username else str(me.id)
    print(f"[userbot] logged in as {who}")
    print(f"[userbot] listening to: {sources}")
    print("[userbot] ready - waiting for CardXabar payment notifications...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
