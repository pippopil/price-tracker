import os
import time
import logging
import requests
from dotenv import load_dotenv
from models import SessionLocal, TrackedProduct
from scraper import extract_product_key

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WORKER_URL = os.getenv("WORKER_URL", "").strip()

# === Формируем базовый URL для API ===
if WORKER_URL:
    API_BASE = WORKER_URL.rstrip("/") + "/"
    logging.info(f"🌐 Worker: {API_BASE}")
else:
    API_BASE = "https://api.telegram.org/"
    logging.warning(f"⚠️ Прямое подключение")

# === Функция для запросов к Bot API ===
def telegram_request(method: str, **params):
    url = f"{API_BASE}bot{TOKEN}/{method}"
    try:
        response = requests.post(url, json=params, timeout=30)
        data = response.json()
        return data.get("result") if data.get("ok") else None
    except Exception as e:
        logging.error(f"💥 Request error: {e}")
        return None

# === Отправка сообщения пользователю ===
def send_message(chat_id: int, text: str, parse_mode="HTML"):
    return telegram_request("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)

# === Логика обработки команд ===
def get_marketplace(url: str) -> str:
    if "ozon.ru" in url: return "ozon"
    if "wildberries.ru" in url: return "wildberries"
    if "market.yandex" in url: return "yandex"
    if "aliexpress" in url: return "aliexpress"
    return ""

def handle_start(chat_id: int):
    send_message(chat_id, "🤖 Привет! Отправь ссылку на товар с Ozon/WB/Yandex/Ali.\nКоманды: /list /stop_all")

def handle_list(chat_id: int):
    db = SessionLocal()
    try:
        items = db.query(TrackedProduct).filter(
            TrackedProduct.user_id == chat_id, 
            TrackedProduct.is_active
        ).all()
        if not items:
            send_message(chat_id, "📭 Пусто.")
            return
        txt = "📦 Отслеживаем:\n" + "\n".join(
            f"{i}. {p.marketplace} | {p.url}" for i, p in enumerate(items, 1)
        )
        send_message(chat_id, txt)
    finally:
        db.close()

def handle_stop_all(chat_id: int):
    db = SessionLocal()
    try:
        db.query(TrackedProduct).filter(
            TrackedProduct.user_id == chat_id
        ).update({"is_active": False})
        db.commit()
        send_message(chat_id, "⛔ Все отслеживания остановлены.")
    finally:
        db.close()

def handle_link(chat_id: int, url: str):
    mp = get_marketplace(url)
    if not mp:
        send_message(chat_id, "❌ Поддерживаются только Ozon, WB, Yandex, AliExpress.")
        return
    
    db = SessionLocal()
    try:
        prod = TrackedProduct(
            user_id=chat_id,
            product_key=extract_product_key(url),
            url=url,
            marketplace=mp
        )
        db.add(prod)
        db.commit()
        send_message(chat_id, f"✅ Добавлено: {mp}\nПроверка цены каждые 10 мин.")
    finally:
        db.close()

# === Обработчик входящих сообщений ===
def process_update(update: dict):
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
    elif text.startswith("http"):
        handle_link(chat_id, text)
    else:
        send_message(chat_id, "❓ Не понял. Отправь ссылку или команду /start")

# === Главный цикл polling ===
def run_polling():
    logging.info("🚀 Запуск long-polling на requests...")
    offset = 0
    
    while True:
        try:
            updates = telegram_request("getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
            if updates:
                for update in updates:
                    offset = update["update_id"] + 1
                    process_update(update)
            time.sleep(1)  # Не спамим запросами
        except KeyboardInterrupt:
            logging.info("🛑 Остановка по запросу пользователя")
            break
        except Exception as e:
            logging.error(f"❌ Ошибка в цикле: {e}")
            time.sleep(5)  # Ждём перед повтором

if __name__ == "__main__":
    # Тестовый запрос при старте
    me = telegram_request("getMe")
    if me:
        logging.info(f"✅ Бот: @{me.get('username')}")
        print(f"✅ Подключено как @{me.get('username')}")
    else:
        logging.error("❌ Не удалось подключиться к Telegram")
        exit(1)
    
    # Запускаем polling
    run_polling()