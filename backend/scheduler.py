import os
import time
import logging
import requests
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from models import SessionLocal, TrackedProduct, PriceHistory
from scraper import fetch_price_mock

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# Загружаем переменные из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WORKER_URL = os.getenv("WORKER_URL", "").strip()

# === Вспомогательные функции ===
def get_telegram_api_url(method: str) -> str:
    """Возвращает правильный URL для вызова Telegram API (через Worker или напрямую)"""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден в .env")
    
    if WORKER_URL:
        base = WORKER_URL.rstrip("/")
        return f"{base}/bot{BOT_TOKEN}/{method}"
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

def send_notification(user_id: int, text: str) -> bool:
    from dotenv import load_dotenv
    import os, requests
    
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    WORKER_URL = os.getenv("WORKER_URL", "").strip()
    
    api_base = WORKER_URL.rstrip("/") + "/" if WORKER_URL else "https://api.telegram.org/"
    url = f"{api_base}bot{TOKEN}/sendMessage"
    
    try:
        response = requests.post(url, json={"chat_id": user_id, "text": text, "parse_mode": "HTML"}, timeout=10)
        return response.status_code == 200 and response.json().get("ok")
    except Exception as e:
        logging.error(f"💥 Ошибка уведомления: {e}")
        return False

# === Основная задача планировщика ===
def update_prices_job():
    """Проверяет цены, сохраняет историю, сравнивает маркетплейсы, шлёт уведомления"""
    logging.info("🔄 Запуск проверки цен...")
    db: Session = SessionLocal()

    try:
        active_products = db.query(TrackedProduct).filter(TrackedProduct.is_active == True).all()
        if not active_products:
            logging.info("📭 Нет активных товаров для отслеживания")
            return

        logging.info(f"📦 Найдено {len(active_products)} активных товаров")
        
        # Группируем цены по product_key для кросс-маркетплейс сравнения
        # Структура: {product_key: {marketplace: price, ...}}
        prices_by_key = {}
        products_by_key = {}

        for prod in active_products:
            try:
                # 1. Получаем новую цену (сейчас заглушка, позже заменим на реальный парсер)
                data = fetch_price_mock(prod.url, prod.marketplace)
                new_price = data["price"]

                # 2. Находим предыдущую цену, чтобы не спамить уведомлениями
                last_history = db.query(PriceHistory).filter(
                    PriceHistory.product_key == prod.product_key,
                    PriceHistory.marketplace == prod.marketplace
                ).order_by(PriceHistory.timestamp.desc()).first()

                prev_price = last_history.price if last_history else None
                price_changed = prev_price is None or abs(new_price - prev_price) > 0.5

                # 3. Сохраняем в историю
                db.add(PriceHistory(
                    product_key=prod.product_key,
                    price=new_price,
                    marketplace=prod.marketplace,
                    timestamp=datetime.utcnow()
                ))

                # 4. Обновляем текущую цену в основной таблице
                prod.current_price = new_price

                # 5. Собираем данные для сравнения
                if prod.product_key not in prices_by_key:
                    prices_by_key[prod.product_key] = {}
                    products_by_key[prod.product_key] = []
                
                prices_by_key[prod.product_key][prod.marketplace] = new_price
                products_by_key[prod.product_key].append((prod, price_changed))

                # Небольшая задержка (этикет для парсинга, позже пригодится)
                time.sleep(0.3)

            except Exception as e:
                logging.error(f"❌ Ошибка проверки {prod.url}: {e}")

        db.commit()

        # 6. Анализ и рассылка уведомлений
        logging.info("📊 Сравнение цен и подготовка уведомлений...")
        for key, marketplace_prices in prices_by_key.items():
            if not marketplace_prices:
                continue

            # Находим лучшую цену среди всех маркетплейсов для этого товара
            best_mp = min(marketplace_prices, key=marketplace_prices.get)
            best_price = marketplace_prices[best_mp]

            for prod, changed in products_by_key[key]:
                # Шлём уведомление, если:
                # а) Цена в этом магазине изменилась > 0.5₽
                # б) ИЛИ другой магазин стал дешевле текущего
                should_notify = changed or (best_mp != prod.marketplace and best_price < (prod.current_price or float('inf')))

                if should_notify:
                    message = (
                        f"📉 <b>Обновление цены!</b>\n"
                        f"🛒 {prod.marketplace.upper()}: {prod.current_price} ₽\n"
                        f"🏆 <b>Дешевле всего:</b> {best_mp} за {best_price} ₽\n"
                        f"🔗 <a href='{prod.url}'>Открыть товар</a>"
                    )
                    send_notification(prod.user_id, message)

        logging.info("✅ Проверка завершена успешно.")

    except Exception as e:
        logging.error(f"💥 Критическая ошибка в планировщике: {e}")
        db.rollback()
    finally:
        db.close()

# === Запуск ===
def start_scheduler():
    """Инициализирует и запускает APScheduler"""
    scheduler = BackgroundScheduler()
    
    # Интервал проверки: 10 минут (для локальных тестов можно поставить minutes=1)
    scheduler.add_job(
        update_prices_job, 
        "interval", 
        minutes=10, 
        id="price_checker", 
        replace_existing=True,
        max_instances=1  # Гарантирует, что задача не запустится дважды, если предыдущая зависла
    )
    
    scheduler.start()
    logging.info("⏱ Планировщик запущен (интервал: 10 мин)")
    return scheduler