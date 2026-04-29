import asyncio
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from models import SessionLocal, TrackedProduct

TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Получите у @BotFather
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# Простой менеджер уведомлений (в продакшене используйте очередь)
_notification_queue = []

async def notify_user(user_id: int, url: str, mp: str, price: float, best: dict):
    msg = (f"📉 Изменение цены!\n"
           f"Маркетплейс: {mp}\n"
           f"Ссылка: {url}\n"
           f"Новая цена: {price} ₽\n"
           f"🏆 Лучше всего: {best['marketplace']} за {best['price']} ₽")
    try:
        await bot.send_message(user_id, msg, parse_mode="HTML")
    except Exception:
        pass

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🤖 Привет! Отправьте мне ссылку на товар с Ozon/Wildberries/Yandex Market/AliExpress.\nДля управления: /list /stop")

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    db = SessionLocal()
    try:
        items = db.query(TrackedProduct).filter(TrackedProduct.user_id == message.from_user.id, TrackedProduct.is_active == True).all()
        if not items:
            await message.answer("📭 Вы ничего не отслеживаете.")
            return
        txt = "📦 Отслеживаемые товары:\n"
        for i, item in enumerate(items, 1):
            txt += f"{i}. {item.marketplace} | {item.url}\n"
        await message.answer(txt, parse_mode="HTML")
    finally:
        db.close()

@router.message(Command("stop"))
async def cmd_stop(message: types.Message):
    await message.answer("Ответьте на сообщение с товаром или введите номер из /list, чтобы отключить отслеживание. (В полной версии будет inline-кнопка)")

@router.message()
async def handle_link(message: types.Message):
    url = message.text.strip()
    mp = ""
    if "ozon.ru" in url: mp = "ozon"
    elif "wildberries.ru" in url: mp = "wildberries"
    elif "market.yandex" in url: mp = "yandex"
    elif "aliexpress" in url: mp = "aliexpress"
    else:
        await message.answer("❌ Поддерживаются только Ozon, Wildberries, Yandex Market, AliExpress.")
        return

    db = SessionLocal()
    try:
        from scraper import extract_product_key
        key = extract_product_key(url, "")
        prod = TrackedProduct(
            user_id=message.from_user.id,
            product_key=key,
            url=url,
            marketplace=mp,
            current_price=None
        )
        db.add(prod)
        db.commit()
        await message.answer(f"✅ Добавлено отслеживание: {mp}\nТовар будет проверяться каждые 10 минут.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        db.close()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())