import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

import asyncio
import json
import os
import re
import time
import hashlib
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
import aiohttp
try:
    import phonenumbers
except ImportError:
    phonenumbers = None

# ================= CONFIGURATION =================
VERSION = "v1.1 - Auto OTP Engine"

BOT_TOKEN       = os.getenv("BOT_TOKEN", "9075278249:AAFyDP34avanKQ5IWJATZJpH6rYTcS8a0ak")
CHANNEL_ID      = os.getenv("CHANNEL_ID", "-1004427004477")
NEW_CHANNEL_ID  = os.getenv("NEW_CHANNEL_ID", "-1003250473765")
PRIVATE_CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID", "-1003956267456")
ADMIN_ID        = int(os.getenv("ADMIN_ID", "8473160748"))

# Blue SMS API Config (Blue-SMS requires at least 2 seconds between requests)
BLUESMS_TOKEN   = os.getenv("BLUESMS_TOKEN", "simple_v2_92WAskHrRh_ai3tmgiraW9bIm5Fa2bEQj30sMV1UV8iGxSHe")
BLUESMS_V2_URL  = "https://agent-api.blue-sms.net/v2/cdr"
POLL_INTERVAL   = float(os.getenv("POLL_INTERVAL", "3.5"))   # 3.5s safe buffer to prevent 429 rate limit

# Button Links
CHANNEL_URL     = os.getenv("CHANNEL_URL", "https://t.me/allnumbersfree")
GET_NUMBER_URL  = os.getenv("GET_NUMBER_URL", "https://t.me/allnumbersfree")

seen_file = "seen_messages.json"
bot_ref = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

# ================= HELPERS & PARSERS =================
def escape_markdown(text):
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = str(text).replace(char, f'\\{char}')
    return text

def region_to_flag(region):
    return "".join(chr(127397 + ord(c)) for c in region.upper())

def get_country(ph):
    if phonenumbers:
        try:
            p = phonenumbers.parse("+" + str(ph).lstrip("+"))
            r = phonenumbers.region_code_for_number(p)
            if r and len(r) == 2:
                return region_to_flag(r), r
        except:
            pass
    return "🌍", "GLOBAL"

def mask(p):
    p = str(p).strip()
    return p if len(p) <= 6 else f"{p[:4]}*****{p[-3:]}"

def extract_otp(t):
    m = re.search(r'\b(\d{4,8})\b', t)
    return m.group(1) if m else "N/A"

def make_dedup_key(num, cli, dt, msg):
    raw = f"{num}:{cli}:{dt}:{msg}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()

def load_seen():
    try:
        if os.path.exists(seen_file):
            with open(seen_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {k: True for k in data[-2000:]}
    except:
        pass
    return {}

def save_seen(seen):
    try:
        with open(seen_file, 'w', encoding='utf-8') as f:
            json.dump(list(seen.keys())[-2000:], f)
    except:
        pass

seen_messages = load_seen()

async def safe_send(bot, chat_id, text, reply_markup=None):
    if not chat_id or str(chat_id).strip() in ["0", "", "None"]:
        return False
    for attempt in range(3):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup,
                read_timeout=15,
                write_timeout=15,
                connect_timeout=15
            )
            return True
        except Exception as e:
            err_str = str(e)
            if "Flood control exceeded" in err_str or "Too Many Requests" in err_str:
                wait_sec = 5
                m = re.search(r'retry after (\d+)', err_str, re.IGNORECASE)
                if m:
                    wait_sec = int(m.group(1)) + 1
                print(f"⏳ Flood wait {wait_sec}s for {chat_id}", flush=True)
                await asyncio.sleep(wait_sec)
                continue
            if "chat not found" in err_str.lower() or "bot was blocked" in err_str.lower():
                return False
            if attempt < 2:
                await asyncio.sleep(1)
            else:
                print(f"❌ Send err [{chat_id}]: {e}", flush=True)
                return False
    return False

async def send_to_all_channels(text, reply_markup=None):
    for cid in [CHANNEL_ID, NEW_CHANNEL_ID, PRIVATE_CHANNEL_ID]:
        if cid and str(cid).strip():
            await safe_send(bot_ref, str(cid).strip(), text, reply_markup)
            await asyncio.sleep(0.15)

# ================= MAIN POLLING ENGINE =================
async def run_bot():
    global seen_messages
    print(f"🚀 {VERSION} STARTING...", flush=True)

    first_run = True
    err_count = 0

    conn = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(connector=conn, headers=HEADERS) as session:
        while True:
            try:
                # Query Simple API v2 for last 20 records
                params = {
                    "token": BLUESMS_TOKEN,
                    "records": 20
                }
                async with session.get(BLUESMS_V2_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 429 or resp.status == 503:
                        print(f"⏳ Rate-limit/Backoff [{resp.status}] — waiting 5s...", flush=True)
                        await asyncio.sleep(5)
                        continue
                    elif resp.status != 200:
                        print(f"⚠️ API Status {resp.status}", flush=True)
                        await asyncio.sleep(POLL_INTERVAL)
                        continue

                    data = await resp.json()
                    if data.get("status") != "success":
                        await asyncio.sleep(POLL_INTERVAL)
                        continue

                    records = data.get("data", [])

                if first_run:
                    first_run = False
                    is_cold_start = (len(seen_messages) == 0)
                    print(f"🔥 Initial boot: {len(records)} records on panel (cold_start={is_cold_start})", flush=True)
                    # Mark existing records as seen on cold start
                    for r in records:
                        num = r.get("num", "")
                        cli = r.get("cli", "")
                        dt  = r.get("dt", "")
                        msg = r.get("message", "")
                        key = make_dedup_key(num, cli, dt, msg)
                        seen_messages[key] = True
                    save_seen(seen_messages)
                    print("✅ Ready! Listening for brand new incoming OTPs...", flush=True)
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                # Process new records
                new_count = 0
                for r in reversed(records):
                    num = str(r.get("num", "")).strip()
                    cli = str(r.get("cli", "SMS")).strip()
                    dt  = str(r.get("dt", "")).strip()
                    msg = str(r.get("message", "")).strip()

                    if not num or not msg:
                        continue

                    key = make_dedup_key(num, cli, dt, msg)
                    if key in seen_messages:
                        continue

                    seen_messages[key] = True
                    new_count += 1

                    otp = extract_otp(msg)
                    masked = mask(num)
                    flag, ccode = get_country(num)

                    clean_masked = escape_markdown(masked)
                    clean_ccode  = escape_markdown(ccode)
                    line1 = f"{flag} {clean_ccode} \\| 🟢 {clean_masked} \\#EN"

                    clean_sender = escape_markdown(cli)
                    if otp and otp != "N/A":
                        clean_otp = escape_markdown(otp)
                        line2 = f"🔥 {clean_sender} \\- `{clean_otp}`"
                    else:
                        line2 = f"🔥 {clean_sender} \\- SMS Received"

                    message_text = f"{line1}\n{line2}"

                    # 1-Click Direct Copy Button for OTP + Channel & Get Number links
                    if otp and otp != "N/A":
                        otp_btn = InlineKeyboardButton(f"🛡️ {otp}", api_kwargs={'copy_text': {'text': str(otp)}})
                    else:
                        otp_btn = InlineKeyboardButton("🛡️ SMS", callback_data="ignore")

                    keyboard = [
                        [InlineKeyboardButton("🔔 Channel", url=CHANNEL_URL), otp_btn],
                        [InlineKeyboardButton("📞 Get Number", url=GET_NUMBER_URL)]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await send_to_all_channels(message_text, reply_markup)
                    print(f"✅ SENT OTP TO CHANNEL: {masked} | {cli} | {otp} [dt={dt}]", flush=True)
                    await asyncio.sleep(0.3)

                if new_count > 0:
                    save_seen(seen_messages)

                err_count = 0

            except Exception as e:
                err_count += 1
                if err_count % 10 == 0:
                    print(f"⚠️ Polling Error ({err_count}): {type(e).__name__} {e}", flush=True)
                await asyncio.sleep(POLL_INTERVAL)

            await asyncio.sleep(POLL_INTERVAL)

# ================= 24/7 CLOUD HEALTH SERVER =================
def start_simple_server():
    import http.server
    import socketserver
    port = int(os.getenv('PORT', 7860))

    class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format, *args):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
            print(f"🌐 Cloud Health Check Server running on port {port}", flush=True)
            httpd.serve_forever()
    except Exception as e:
        print(f"Server notice: {e}", flush=True)

async def web_server():
    await asyncio.to_thread(start_simple_server)

# ================= ENTRYPOINT =================
async def main():
    global bot_ref

    app = Application.builder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    bot_ref = app.bot

    await app.initialize()
    await app.start()

    print(f"✅ Bot {VERSION} initialized successfully", flush=True)

    asyncio.create_task(web_server())
    asyncio.create_task(run_bot())
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("STOPPED", flush=True)
