# language: Python, file: main.py (дополнение)
import io, zipfile, pathlib
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ============================================================
# ПАПКА СО СБОРКОЙ (на Render — /opt/render/project/src/dist/)
# ============================================================
BUILD_DIR = pathlib.Path(os.getenv("BUILD_DIR", "build"))

def build_zip() -> bytes:
    """
    Берёт setup.exe и payload.bin из BUILD_DIR, кладёт в zip.
    Возвращает байты архива.
    """
    setup   = BUILD_DIR / "setup.exe"
    payload = BUILD_DIR / "payload.bin"
    readme  = BUILD_DIR / "readme.txt"

    if not setup.exists() or not payload.exists():
        missing = []
        if not setup.exists():   missing.append("setup.exe")
        if not payload.exists(): missing.append("payload.bin")
        raise FileNotFoundError(", ".join(missing))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(setup,   arcname="setup.exe")
        z.write(payload, arcname="payload.bin")
        if readme.exists():
            z.write(readme, arcname="readme.txt")
    buf.seek(0)
    return buf.read()

# ============================================================
# КОМАНДЫ БОТА
# ============================================================
@dp.message(Command("get"))
async def cmd_get(msg: Message):
    """Отправить сборку zip'ом."""
    if msg.from_user.id != ADMIN_ID: return
    try:
        blob = build_zip()
        await msg.answer_document(
            BufferedInputFile(blob, filename="build.zip"),
            caption="📦 сборка готова",
        )
    except FileNotFoundError as e:
        await msg.answer(f"[-] нет файлов: {e}")
    except Exception as e:
        await msg.answer(f"[-] ошибка сборки: {e}")

@dp.message(Command("get_fake"))
async def cmd_get_fake(msg: Message):
    """Отправить только setup.exe — «фейк», если payload.bin ещё нет."""
    if msg.from_user.id != ADMIN_ID: return
    setup = BUILD_DIR / "setup.exe"
    if not setup.exists():
        await msg.answer("[-] setup.exe не найден")
        return
    blob = setup.read_bytes()
    await msg.answer_document(
        BufferedInputFile(blob, filename="setup.exe"),
        caption="📦 setup.exe",
    )

@dp.message(Command("list"))
async def cmd_list(msg: Message):
    """Показать, что лежит в build/."""
    if msg.from_user.id != ADMIN_ID: return
    if not BUILD_DIR.exists():
        await msg.answer("build/ не существует")
        return
    files = []
    for p in sorted(BUILD_DIR.iterdir()):
        size = p.stat().st_size
        files.append(f"`{p.name}` — {size/1024:.1f} KB")
    if not files:
        await msg.answer("пусто")
        return
    await msg.answer("build/\n" + "\n".join(files), parse_mode="Markdown")
