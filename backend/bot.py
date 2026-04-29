"""
bot.py — Telegram-бот для управления отслеживанием цен

Особенности:
- Работает через Cloudflare Worker (обход блокировок)
- Использует long-polling на requests (не aiogram start_polling)
- Команды: /start, /list, /stop_all
- Принимает ссылки на товары для отслеживания
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv

from models import SessionLocal, TrackedProduct, init_db
from scraper import extract_product_key

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

load_dotenv()

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("BOT_TOKEN")
WORKER_URL = os.getenv("WORKER_URL", "").strip()

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан в .env")

# Формируем базовый URL для API
if WORKER_URL:
    API_BASE = WORKER_URL.rstrip("/") + "/"
    logging.info(f"🌐 Режим: Cloudflare Worker → {API_BASE}")
else:
    API_BASE = "https://api.telegram.org/"
    logging.warning(f"⚠️ Режим: Прямое подключение → {API_BASE}")


def _telegram_request(method: str, **params) -> dict:
    """Делает запрос к Telegram Bot API через requests"""
    url = f"{API_BASE}bot{TOKEN}/{method}"
    try:
        response = requests.post(url, json=params, timeout=30)
        data = response.json()
        return data if data.get("ok") else None
    except Exception as e:
        logging.error(f"💥 Request error: {e}")
        return None


def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Отправляет сообщение пользователю"""
    result = _telegram_request("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)
    return result is not None


# ===== ОБРАБОТКА КОМАНД =====
def get_marketplace(url: str) -> str:
    """Определяет маркетплейс по ссылке"""
    url_lower = url.lower()
    if "ozon.ru" in url_lower:
        return "ozon"
    if "wildberries.ru" in url_lower:
        return "wildberries"
    if "market.yandex.ru" in url_lower or "yandex.ru/market" in url_lower:
        return "yandex"
    if "aliexpress" in url_lower:
        return "aliexpress"
    return ""


def handle_start(chat_id: int):
    send_message(chat_id, (
        "🤖 <b>Привет! Я бот для отслеживания цен.</b>\n\n"
        "📦 <b>Что умею:</b>\n"
        "• Отслеживать цены на Ozon, Wildberries, Яндекс.Маркет, AliExpress\n"
        "• Сравнивать цены между маркетплейсами\n"
        "• Присылать уведомления при изменении цены\n\n"
        "🔗 <b>Как использовать:</b>\n"
        "1. Отправь мне ссылку на товар\n"
        "2. Я добавлю его в отслеживание\n"
        "3. Буду присылать уведомления при изменении цены\n\n"
        "⚙️ <b>Команды:</b>\n"
        "/list — показать мои товары\n"
        "/stop_all — остановить все отслеживания"
    ))


def handle_list(chat_id: int):
    db = SessionLocal()
    try:
        items = db.query(TrackedProduct).filter(
            TrackedProduct.user_id == chat_id,
            TrackedProduct.is_active == True
        ).all()
        
        if not items:
            send_message(chat_id, "📭 У вас пока нет отслеживаемых товаров.\nОтправьте ссылку на товар, чтобы начать.")
            return
        
        lines = [f"📦 <b>Ваши товары ({len(items)}):</b>"]
        for i, item in enumerate(items, 1):
            price = f"{item.current_price} ₽" if item.current_price else "???"
            lines.append(f"{i}. {item.marketplace.upper()} | {price} | {item.url[:50]}...")
        
        send_message(chat_id, "\n".join(lines))
    finally:
        db.close()


def handle_stop_all(chat_id: int):
    db = SessionLocal()
    try:
        count = db.query(TrackedProduct).filter(
            TrackedProduct.user_id == chat_id
        ).update({"is_active": False})
        db.commit()
        send_message(chat_id, f"⛔ Остановлено отслеживание {count} товаров.")
    finally:
        db.close()


def handle_link(chat_id: int, url: str):
    mp = get_marketplace(url)
    if not mp:
        send_message(chat_id, (
            "❌ <b>Неподдерживаемый маркетплейс.</b>\n\n"
            "Поддерживаются:\n"
            "• Ozon (ozon.ru)\n"
            "• Wildberries (wildberries.ru)\n"
            "• Яндекс.Маркет (market.yandex.ru)\n"
            "• AliExpress (aliexpress.ru)"
        ))
        return
    
    db = SessionLocal()
    try:
        # Проверяем, нет ли уже такого товара
        existing = db.query(TrackedProduct).filter(
            TrackedProduct.user_id == chat_id,
            TrackedProduct.url == url,
            TrackedProduct.is_active == True
        ).first()
        
        if existing:
            send_message(chat_id, f"ℹ️ Этот товар уже отслеживается ({mp.upper()}).")
            return
        
        # Добавляем новый товар
        prod = TrackedProduct(
            user_id=chat_id,
            product_key=extract_product_key(url),
            url=url,
            marketplace=mp,
            current_price=None
        )
        db.add(prod)
        db.commit()
        
        send_message(chat_id, (
            f"✅ <b>Добавлено отслеживание!</b>\n"
            f"🛒 Маркетплейс: {mp.upper()}\n"
            f"🔗 Ссылка: {url[:60]}...\n\n"
            f"⏱ Первая проверка цены через {os.getenv('CHECK_INTERVAL', 10)} минут.\n"
            f"Вы получите уведомление, если цена изменится."
        ))
    finally:
        db.close()


def process_update(update: dict):
    """Обрабатывает входящее обновление от Telegram"""
    if "message" not in update:
        return
    
    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    
    if text == "/start":
        handle_start(chat_id)
    elif text == "/list":
        handle_list(chat_id)
    elif text == "/stop_all":
        handle_stop_all(chat_id)
    elif text.startswith("http://") or text.startswith("https://"):
        handle_link(chat_id, text)
    else:
        send_message(chat_id, "❓ Не понял команду.\nОтправьте ссылку на товар или /start для справки.")


def run_polling():
    """Основной цикл long-polling"""
    logging.info("🚀 Запуск long-polling...")
    offset = 0
    error_count = 0
    
    while True:
        try:
            # Запрашиваем обновления
            updates = _telegram_request(
                "getUpdates",
                offset=offset,
                timeout=30,
                allowed_updates=["message"]
            )
            
            if updates:
                error_count = 0  # Сбрасываем счётчик ошибок при успехе
                
                for update in updates:
                    offset = update["update_id"] + 1
                    process_update(update)
            else:
                # Нет новых сообщений — ждём
                time.sleep(1)
                
        except KeyboardInterrupt:
            logging.info("🛑 Остановка по запросу пользователя")
            break
        except Exception as e:
            error_count += 1
            logging.error(f"❌ Ошибка в цикле (попытка {error_count}): {e}")
            
            if error_count > 5:
                logging.warning("⚠️ Много ошибок, делаем паузу 30 сек...")
                time.sleep(30)
                error_count = 0
            else:
                time.sleep(5)


if __name__ == "__main__":
    # Инициализация БД
    init_db()
    
    # Тестовый запрос при старте
    logging.info("📡 Проверка соединения с Telegram...")
    me = _telegram_request("getMe")
    
    if me:
        username = me.get("username", "unknown")
        logging.info(f"✅ Бот подключён: @{username}")
        print(f"\n✅ Подключено как @{username}")
        print("📬 Ожидание сообщений... (нажми Ctrl+C для остановки)\n")
    else:
        logging.error("❌ Не удалось подключиться к Telegram")
        print("❌ Ошибка подключения. Проверьте BOT_TOKEN и WORKER_URL в .env")
        exit(1)
    
    # Запускаем polling
    run_polling()