import logging
import asyncio
import random
import os
import threading
import time
import datetime
import psutil 
import gc 
import ctypes 
from flask import Flask, Response
from telegram import Update
from telegram.error import RetryAfter, Forbidden
from telegram.ext import Application, MessageHandler, ContextTypes, filters

# ─── LOGGING FIX ───
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING) 

# ─── FLASK WEB SERVER ───
web_app = Flask(__name__)
@web_app.route('/')
def home(): return Response("NC BOT IS ALIVE!", status=200, mimetype='text/plain')
def run_web(): 
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port, threaded=True)

# ─── CONFIGURATION ───
OWNER_ID = int(os.environ.get("OWNER_ID", "0")) 
DELAY = 0.3  
EMOJIS = ["🔥", "⚡", "💀", "🚀", "🌞", "✅", "💋", "😝"]

# ─── STATUS VARIABLES ───
START_TIME = time.time()
TOTAL_NC_RENAMES = 0
LAST_PURGE_SLOT = None 
RENDER_LIMIT = 512.0 

# ─── CONTROLLER & MEMORY ───
NC_STATES = {} 

class Controller:
    def __init__(self):
        self.active = {}

    def stop_chat(self, chat_id):
        if chat_id in self.active:
            tasks = self.active.pop(chat_id)
            for task in tasks:
                if not task.done():
                    task.cancel()

    def stop_all(self):
        for cid in list(self.active.keys()):
            self.stop_chat(cid)

ctrl = Controller()
bots = []

# ─── NC LOOP ───
async def nc_loop(bot, chat_id, text):
    global TOTAL_NC_RENAMES
    while True:
        try:
            e = random.choice(EMOJIS)
            title = f"{e}{text}{e}"[:255]
            await bot.set_chat_title(chat_id=chat_id, title=title)
            TOTAL_NC_RENAMES += 1 
            await asyncio.sleep(DELAY)
            
        except asyncio.CancelledError:
            break 
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1) 
        except Forbidden:
            break 
        except Exception as e:
            await asyncio.sleep(2) 

# ─── ULTIMATE DEEP CLEAN FUNCTION ───
def ultimate_deep_clean():
    for _ in range(3):
        gc.collect()
    
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception as e:
        logger.error(f"malloc_trim failed: {e}")

# ─── SMART AUTO PURGE SCHEDULER ───
async def smart_purge_scheduler():
    global LAST_PURGE_SLOT
    while True:
        await asyncio.sleep(60) 
        
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz)
        
        process = psutil.Process(os.getpid())
        current_ram = process.memory_info().rss / (1024 * 1024)
        
        emergency_purge = current_ram > 400.0
        current_slot = f"{now_ist.date()}_{now_ist.hour}"
        time_purge = (now_ist.hour in [7, 19]) and (LAST_PURGE_SLOT != current_slot)

        if emergency_purge or time_purge:
            reason = "Emergency (RAM > 400MB)" if emergency_purge else "Scheduled (7 AM/PM)"
            logger.info(f"Starting Purge: {reason}...")
            
            mem_before = current_ram
            ctrl.stop_all()
            ctrl.active.clear()
            ultimate_deep_clean()
            
            for chat_id, text in NC_STATES.items():
                ctrl.active[chat_id] = []
                for b in bots:
                    task = asyncio.create_task(nc_loop(b['bot'], chat_id, text))
                    ctrl.active[chat_id].append(task)
            
            if time_purge:
                LAST_PURGE_SLOT = current_slot
                
            mem_after = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            logger.info(f"Purge Completed. RAM: {mem_before:.1f}MB -> {mem_after:.1f}MB")
            
            try:
                if bots:
                    msg_text = (
                        f"🧹 <b>Ultimate Deep Purge Completed!</b>\n"
                        f"<i>Reason: {reason}</i>\n\n"
                        f"📉 <b>Memory Cleaned:</b>\n"
                        f"• Before: {mem_before:.1f} MB\n"
                        f"• After: <b>{mem_after:.1f} MB</b>\n"
                        f"• Freed: {(mem_before - mem_after):.1f} MB\n\n"
                        f"✅ All commands restarted."
                    )
                    await bots[0]['bot'].send_message(OWNER_ID, msg_text, parse_mode='HTML')
            except: pass

# ─── COMMAND ROUTER ───
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    text = msg.text or ""
    
    # Sirf '$' se shuru hone wale messages check karega
    if not text.startswith("$"): return

    user = update.effective_user
    
    # ─── OWNER ONLY CHECK (STRICT) ───
    if not user or user.id != OWNER_ID: 
        return 

    parts = text.split(maxsplit=1)
    cmd = parts[0][1:].split("@")[0].lower() 
    args = parts[1].split() if len(parts) > 1 else []

    if cmd == "nc":
        if not args: return await msg.reply_text("Usage: $nc <text>")
        target = ' '.join(args)
        chat_id = update.effective_chat.id
        
        ctrl.stop_chat(chat_id)
        ctrl.active[chat_id] = []
        NC_STATES[chat_id] = target
        
        for b in bots:
            task = asyncio.create_task(nc_loop(b['bot'], chat_id, target))
            ctrl.active[chat_id].append(task)
            
        await msg.reply_text(f"✅ NC STARTED: {target}\n⚡ Speed: {DELAY}s")

    elif cmd == "stop":
        chat_id = update.effective_chat.id
        if ctrl.active.get(chat_id):
            ctrl.stop_chat(chat_id)
            NC_STATES.pop(chat_id, None) 
            await msg.reply_text("🛑 STOPPED")
        else:
            await msg.reply_text("⚠️ NO ACTIVE NC")

    elif cmd == "status":
        uptime_seconds = int(time.time() - START_TIME)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days > 0 else f"{hours}h {minutes}m {seconds}s"

        process = psutil.Process(os.getpid())
        bot_ram = process.memory_info().rss / (1024 * 1024)
        ram_percent = (bot_ram / RENDER_LIMIT) * 100
        free_ram = RENDER_LIMIT - bot_ram

        filled = int(ram_percent / 10)
        if filled > 10: filled = 10
        meter = "■" * filled + "□" * (10 - filled)

        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz)
        
        if now_ist.hour < 7:
            next_purge = now_ist.replace(hour=7, minute=0, second=0, microsecond=0)
        elif now_ist.hour < 19:
            next_purge = now_ist.replace(hour=19, minute=0, second=0, microsecond=0)
        else:
            next_purge = now_ist.replace(hour=7, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
            
        time_left = next_purge - now_ist
        h_left, r = divmod(time_left.seconds, 3600)
        m_left, s_left = divmod(r, 60)
        next_purge_str = next_purge.strftime("%d-%b %I:%M %p")

        status_text = (
            f"📊 <b>RENDER ULTIMATE STATUS (512MB)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💾 <b>Bot Memory Usage:</b>\n"
            f"• Limit: <b>512.0 MB</b>\n"
            f"• Used: <b>{bot_ram:.1f} MB</b> ({ram_percent:.1f}%)\n"
            f"• Free: {free_ram:.1f} MB\n"
            f"• Meter: [{meter}] {ram_percent:.1f}%\n\n"
            f"🧹 <b>Deep Purge (7 AM & 7 PM):</b>\n"
            f"• Next Clean: <b>{next_purge_str}</b>\n"
            f"• Time Left: <b>{h_left}h {m_left}m {s_left}s</b>\n"
            f"• Emergency Purge: Active (>400MB)\n\n"
            f"⚙️ <b>Bot Engine:</b>\n"
            f"• Active GCs: {len(ctrl.active)}\n"
            f"• Total Renames: {TOTAL_NC_RENAMES}\n"
            f"• Uptime: {uptime_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await msg.reply_text(status_text, parse_mode='HTML')

# ─── MAIN RUNNER ───
async def run_bot(tok):
    try:
        app = Application.builder().token(tok).connect_timeout(10).read_timeout(30).build()
        me = await app.bot.get_me()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
        app.add_handler(MessageHandler(filters.COMMAND, router))
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True) 
        
        bots.append({'id': me.id, 'bot': app.bot, 'app': app})
        print(f"✅ Started @{me.username}")
        await asyncio.Event().wait() 
    except Exception as e:
        print(f"❌ Fail: {e}")

async def main():
    print("[*] Starting Web Server...")
    threading.Thread(target=run_web, daemon=True).start()

    tok = os.environ.get("BOT_TOKEN")
    if not tok:
        print("[!] ERROR: BOT_TOKEN not found in Render.")
        return

    print(f"[*] Starting Bot with fixed {DELAY}s delay...")
    asyncio.create_task(smart_purge_scheduler())
    await run_bot(tok.strip())

if __name__ == "__main__":
    asyncio.run(main())
