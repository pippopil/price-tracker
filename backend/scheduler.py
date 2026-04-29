from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from models import SessionLocal, TrackedProduct, PriceHistory
from scraper import fetch_price_mock, extract_product_key, normalize_title, find_best_price
from bot import notify_user
import logging

logging.basicConfig(level=logging.INFO)
scheduler = AsyncIOScheduler()

def update_prices():
    db: Session = SessionLocal()
    try:
        active_products = db.query(TrackedProduct).filter(TrackedProduct.is_active == True).all()
        for prod in active_products:
            try:
                data = fetch_price_mock(prod.url, prod.marketplace)
                prod.current_price = data["price"]
                history = PriceHistory(
                    product_key=prod.product_key,
                    price=data["price"],
                    marketplace=prod.marketplace
                )
                db.add(history)
                
                # Проверка на изменение
                if prod.current_price and abs(prod.current_price - (prod.current_price or 0)) > 0.1:
                    best = find_best_price(prod.product_key, db)
                    if best:
                        notify_user(prod.user_id, prod.url, prod.marketplace, data["price"], best)
            except Exception as e:
                logging.error(f"Ошибка обновления {prod.url}: {e}")
        db.commit()
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(update_prices, 'interval', minutes=10)  # Каждые 10 мин
    scheduler.start()