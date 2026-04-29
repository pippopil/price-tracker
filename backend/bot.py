import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from models import SessionLocal, TrackedProduct
from scraper import extract_product_key

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("BOT_PROXY", "").strip()

def create_session_with_fallback(proxy_url: str):
    """Создаёт сессию с прокси, но если он не работает — падает на прямое подключение"""
    if not proxy_url:
        print("⚠️ Прокси не указан. Подключаемся напрямую.")
        return AiohttpSession()
    
    if not (proxy_url.startswith("http://") or proxy_url.startswith("socks5://")):
        print(f"❌ Ошибка формата прокси: '{proxy_url}'")
        print("💡 Должно начинаться с http:// или socks5://")
        return AiohttpSession()
    
    try:
        session = AiohttpSession(proxy=proxy_url)
        print("🌍 Попытка подключения через прокси...")
        return session
    except Exception as e:
        print(f"❌ Не удалось инициализировать прокси: {e}")
        print("🔄 Используем прямое подключение")
        return AiohttpSession()

# Создаём сессию
session = create_session_with_fallback(PROXY_URL)
bot = Bot(token=TOKEN, session=session)
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
    try:
        await dp.start_polling(bot)
    except TelegramNetworkError as e:
        if "502" in str(e) or "Proxy" in str(e):
            print("🔁 Сетевая ошибка прокси. Перезапускаю бот с прямым подключением...")
            # Пересоздаём бота без прокси и перезапускаем
            global bot, session
            session = AiohttpSession()
            bot = Bot(token=TOKEN, session=session)
            await dp.start_polling(bot)
        else:
            raise

if __name__ == "__main__":
    asyncio.run(main())