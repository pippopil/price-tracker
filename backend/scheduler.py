"""
scheduler.py — Планировщик проверок цен

Задачи:
- Периодически проверять цены отслеживаемых товаров
- Сохранять историю в БД
- Отправлять уведомления при изменении цены
- Находить лучшую цену среди маркетплейсов
"""

import os
import time
import logging
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from models import SessionLocal, TrackedProduct, PriceHistory
from scraper import fetch_price

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# Настройки
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL", "10"))  # Интервал проверки
PRICE_DELTA_THRESHOLD = 0.5  # Минимальное изменение цены для уведомления (в рублях)


def _get_telegram_url(method: str) -> str:
    """Возвращает URL для Telegram API (через Worker или напрямую)"""
    token = os.getenv("BOT_TOKEN")
    worker = os.getenv("WORKER_URL", "").strip()
    
    if worker:
        return f"{worker.rstrip('/')}/bot{token}/{method}"
    return f"https://api.telegram.org/bot{token}/{method}"


def send_notification(user_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Отправляет уведомление в Telegram через прямой HTTP-запрос"""
    if not os.getenv("BOT_TOKEN"):
        logging.warning("⚠️ BOT_TOKEN не задан, уведомление пропущено")
        return False
    
    url = _get_telegram_url("sendMessage")
    payload = {"chat_id": user_id, "text": text, "parse_mode": parse_mode}
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            logging.info(f"✅ Уведомление отправлено пользователю {user_id}")
            return True
        logging.error(f"❌ Telegram API: {resp.status_code} - {resp.text[:200]}")
        return False
    except Exception as e:
        logging.error(f"💥 Ошибка отправки уведомления: {e}")
        return False


def _find_best_price(product_key: str, db: Session) -> dict:
    """Находит минимальную цену по product_key среди всех маркетплейсов"""
    latest = {}
    
    # Берем последние записи за последние 24 часа
    cutoff = datetime.utcnow() - timedelta(hours=24)
    records = db.query(PriceHistory).filter(
        PriceHistory.product_key == product_key,
        PriceHistory.timestamp >= cutoff
    ).all()
    
    for rec in records:
        if rec.marketplace not in latest or rec.price < latest[rec.marketplace]["price"]:
            latest[rec.marketplace] = {"price": rec.price, "ts": rec.timestamp}
    
    if not latest:
        return None
    
    best_mp = min(latest, key=lambda m: latest[m]["price"])
    return {
        "marketplace": best_mp,
        "price": latest[best_mp]["price"],
        "all_prices": latest
    }


def update_prices_job():
    """Основная задача: проверка цен всех активных товаров"""
    logging.info(f"🔄 Запуск проверки цен (интервал: {CHECK_INTERVAL_MINUTES} мин)...")
    db: Session = SessionLocal()
    
    try:
        active = db.query(TrackedProduct).filter(
            TrackedProduct.is_active == True
        ).all()
        
        if not active:
            logging.info("📭 Нет активных товаров для отслеживания")
            return
        
        logging.info(f"📦 Проверка {len(active)} товаров...")
        prices_by_key = {}  # {product_key: {mp: price}}
        products_by_key = {}  # {product_key: [TrackedProduct, ...]}
        
        for prod in active:
            try:
                # 1. Получаем новую цену
                data = fetch_price(prod.url, prod.marketplace)
                if not data or data.get("price") is None:
                    logging.warning(f"⚠️ Не удалось получить цену: {prod.url[:60]}")
                    continue
                
                new_price = data["price"]
                
                # 2. Проверяем, изменилась ли цена
                prev = db.query(PriceHistory).filter(
                    PriceHistory.product_key == prod.product_key,
                    PriceHistory.marketplace == prod.marketplace
                ).order_by(PriceHistory.timestamp.desc()).first()
                
                prev_price = prev.price if prev else None
                price_changed = prev_price is None or abs(new_price - prev_price) > PRICE_DELTA_THRESHOLD
                
                # 3. Сохраняем в историю
                db.add(PriceHistory(
                    product_key=prod.product_key,
                    price=new_price,
                    marketplace=prod.marketplace,
                    currency="RUB",
                    available=data.get("available", True),
                    timestamp=datetime.utcnow()
                ))
                
                # 4. Обновляем текущую цену
                prod.current_price = new_price
                if data.get("title") and not prod.title:
                    prod.title = data["title"][:200]  # Кэшируем название
                
                # 5. Собираем для сравнения
                if prod.product_key not in prices_by_key:
                    prices_by_key[prod.product_key] = {}
                    products_by_key[prod.product_key] = []
                
                prices_by_key[prod.product_key][prod.marketplace] = new_price
                products_by_key[prod.product_key].append((prod, price_changed, data.get("available", True)))
                
                # Этикет: небольшая задержка
                time.sleep(0.5)
                
            except Exception as e:
                logging.error(f"❌ Ошибка проверки {prod.url[:60]}: {e}")
                continue
        
        db.commit()
        
        # 6. Анализ и уведомления
        logging.info("📊 Анализ цен и подготовка уведомлений...")
        notified = set()  # Чтобы не спамить одного пользователя
        
        for key, mp_prices in prices_by_key.items():
            if not mp_prices:
                continue
            
            best = _find_best_price(key, db)
            if not best:
                continue
            
            for prod, changed, available in products_by_key[key]:
                # Условие уведомления:
                # - цена в этом магазине изменилась, ИЛИ
                # - другой магазин стал дешевле текущего
                should_notify = (
                    changed or 
                    (best["marketplace"] != prod.marketplace and best["price"] < (prod.current_price or float('inf')))
                ) and prod.user_id not in notified
                
                if should_notify and available:
                    message = (
                        f"📉 <b>Цена обновлена!</b>\n"
                        f"🛒 {prod.marketplace.upper()}: {prod.current_price} ₽\n"
                        f"🏆 <b>Лучшая цена:</b> {best['marketplace']} за {best['price']} ₽\n"
                        f"🔗 <a href='{prod.url}'>Открыть товар</a>"
                    )
                    if send_notification(prod.user_id, message):
                        notified.add(prod.user_id)
        
        logging.info(f"✅ Проверка завершена. Уведомлений отправлено: {len(notified)}")
        
    except Exception as e:
        logging.error(f"💥 Критическая ошибка в планировщике: {e}")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    """Инициализирует и запускает APScheduler"""
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(
        update_prices_job,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id="price_checker",
        replace_existing=True,
        max_instances=1  # Не запускать новую задачу, если старая ещё работает
    )
    
    scheduler.start()
    logging.info(f"⏱ Планировщик запущен (интервал: {CHECK_INTERVAL_MINUTES} мин)")
    return scheduler


# Для отладки: запуск задачи вручную
if __name__ == "__main__":
    logging.info("🧪 Запуск проверки в режиме отладки...")
    update_prices_job()