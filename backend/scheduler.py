import time
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from models import SessionLocal, TrackedProduct, PriceHistory
from scraper import fetch_price_mock
import logging

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8587082849:AAH-m4oWVakOb7uhN4ns5m-YH-pNzGI7PQA"  # Заменишь на тот же токен

def notify_user(user_id: int, url: str, mp: str, price: float, best_mp: str, best_price: float):
    text = f"📉 Цена изменилась!\n{mp}: {price} ₽\n🏆 Дешевле всего: {best_mp} за {best_price} ₽\n🔗 {url}"
    url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url_api, json={"chat_id": user_id, "text": text, "parse_mode": "HTML"})
    except Exception: pass

def update_prices():
    db: Session = SessionLocal()
    try:
        active = db.query(TrackedProduct).filter(TrackedProduct.is_active == True).all()
        for prod in active:
            data = fetch_price_mock(prod.url, prod.marketplace)
            prod.current_price = data["price"]
            db.add(PriceHistory(product_key=prod.product_key, price=data["price"], marketplace=prod.marketplace))
            
            # Поиск лучшей цены среди всех маркетплейсов для этого товара
            history = db.query(PriceHistory).filter(PriceHistory.product_key == prod.product_key).all()
            best = min(history, key=lambda x: x.price)
            if abs(data["price"] - (prod.current_price or 0)) > 0.5:
                notify_user(prod.user_id, prod.url, prod.marketplace, data["price"], best.marketplace, best.price)
        db.commit()
        logging.info(f"✅ Проверено {len(active)} товаров")
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
    finally: db.close()

def start_scheduler():
    sched = BackgroundScheduler()
    sched.add_job(update_prices, 'interval', minutes=10)  # Для теста можно поставить 1
    sched.start()
    logging.info("⏱ Планировщик запущен")