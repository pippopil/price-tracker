import asyncio
import re
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from models import SessionLocal, TrackedProduct
from scraper import extract_product_key

TOKEN = "8587082849:AAH-m4oWVakOb7uhN4ns5m-YH-pNzGI7PQA"  # Заменишь позже
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

def get_marketplace(url: str) -> str:
    if "ozon.ru" in url: return "ozon"
    if "wildberries.ru" in url: return "wildberries"
    if "market.yandex" in url: return "yandex"
    if "aliexpress" in url: return "aliexpress"
    return ""

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🤖 Привет! Отправь ссылку на товар с Ozon/WB/Yandex/Ali.\nКоманды: /list /stop_all")

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    db = SessionLocal()
    try:
        items = db.query(TrackedProduct).filter(TrackedProduct.user_id == message.from_user.id, TrackedProduct.is_active).all()
        if not items: return await message.answer("📭 Пусто.")
        txt = "📦 Отслеживаем:\n" + "\n".join(f"{i}. {p.marketplace} | {p.url}" for i, p in enumerate(items, 1))
        await message.answer(txt)
    finally: db.close()

@router.message(Command("stop_all"))
async def cmd_stop(message: types.Message):
    db = SessionLocal()
    try:
        db.query(TrackedProduct).filter(TrackedProduct.user_id == message.from_user.id).update({"is_active": False})
        db.commit()
        await message.answer("⛔ Все отслеживания остановлены.")
    finally: db.close()

@router.message()
async def handle_link(message: types.Message):
    url = message.text.strip()
    mp = get_marketplace(url)
    if not mp: return await message.answer("❌ Поддерживаются только Ozon, WB, Yandex, AliExpress.")
    
    db = SessionLocal()
    try:
        prod = TrackedProduct(user_id=message.from_user.id, product_key=extract_product_key(url), url=url, marketplace=mp)
        db.add(prod)
        db.commit()
        await message.answer(f"✅ Добавлено: {mp}\nПроверка цены каждые 10 мин.")
    finally: db.close()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())