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
CARDXABAR_SOURCE = os.getenv("CARDXABAR_SOURCE", "").strip()
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
PAYMENT_SECRET = os.getenv("PAYMENT_SECRET", "")
CARD_LAST4 = os.getenv("CARD_LAST4", "").strip()
WEBHOOK_PATH = "/api/payments/cardxabar"

def _sources():
    names, ids = set(), set()
    for part in CARDXABAR_SOURCE.split(","):
        p = part.strip().lstrip("@")
        if not p:
            continue
        if p.lstrip("-").isdigit():
            ids.add(int(p))
        else:
            names.add(p.lower())
    return names, ids

ALLOWED_NAMES, ALLOWED_IDS = _sources()
_PLUS = re.compile(r"[\u2795\uFF0B+]")
_NUMBER = re.compile(r"[0-9][0-9\s\u00a0.,]*[0-9]|[0-9]")

def parse_amount_to_tiyin(text):
    credit_line = None
    for line in text.splitlines():
        if _PLUS.search(line) and any(c.isdigit() for c in line):
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
    resp = requests.post(
        f"{BACKEND_URL}{WEBHOOK_PATH}",
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

async def _is_allowed(event):
    if not ALLOWED_NAMES and not ALLOWED_IDS:
        return True
    try:
        sender = await event.get_sender()
    except Exception:
        sender = None
    uname = (getattr(sender, "username", None) or "").lower()
    sid = getattr(sender, "id", None)
    cid = getattr(event, "chat_id", None)
    return (uname in ALLOWED_NAMES) or (sid in ALLOWED_IDS) or (cid in ALLOWED_IDS)

async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"[userbot] logged in as @{me.username or me.id}")
    try:
        await client.get_dialogs()
        print("[userbot] chat list loaded")
    except Exception as exc:
        print(f"[userbot] get_dialogs warning: {exc}")

    @client.on(events.NewMessage())
    async def handler(event):
        if not await _is_allowed(event):
            return
        text = event.raw_text or ""
        print(f"[userbot] message from source: {text[:150]!r}")
        if CARD_LAST4 and CARD_LAST4 not in text:
            print("[userbot] card last4 filter did not match; skipping")
            return
        tiyin = parse_amount_to_tiyin(text)
        if not tiyin:
            print("[userbot] could not parse a credit amount; skipping")
            return
        print(f"[userbot] incoming credit detected: {tiyin} tiyin")
        await notify_backend(tiyin, text)

    print(f"[userbot] listening: names={sorted(ALLOWED_NAMES)} ids={sorted(ALLOWED_IDS)}")
    print("[userbot] ready - waiting for CardXabar payment notifications...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
