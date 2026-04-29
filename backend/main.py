"""
main.py — FastAPI сервер для веб-интерфейса

Маршруты:
- POST /track/ — добавить товар на отслеживание
- GET /products/{user_id} — список товаров пользователя
- POST /stop/{track_id} — остановить отслеживание
- GET /health — проверка здоровья API
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from models import SessionLocal, TrackedProduct, PriceHistory, init_db
from scraper import extract_product_key, fetch_price
from scheduler import start_scheduler

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ===== LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте приложения"""
    # Инициализация БД
    init_db()
    
    # Запуск планировщика
    start_scheduler()
    
    yield
    # Очистка при остановке (если нужно)
    logging.info("🛑 Приложение остановлено")


# ===== ПРИЛОЖЕНИЕ =====
app = FastAPI(
    title="Price Tracker API",
    description="API для отслеживания цен на маркетплейсах",
    version="1.0.0",
    lifespan=lifespan
)

# CORS (разрешаем запросы с фронтенда)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажи конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== МОДЕЛИ ЗАПРОСОВ =====
class TrackRequest(BaseModel):
    url: HttpUrl
    user_id: int  # Telegram chat_id


class TrackResponse(BaseModel):
    status: str
    product_key: str
    marketplace: str
    message: str


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def get_db():
    """Зависимость для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===== МАРШРУТЫ =====
@app.get("/health")
def health_check():
    """Проверка здоровья API"""
    return {"status": "ok", "service": "price-tracker"}


@app.post("/track/", response_model=TrackResponse)
def track_product(req: TrackRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Добавить товар на отслеживание"""
    url = str(req.url)
    mp = get_marketplace(url)
    
    if not mp:
        raise HTTPException(400, detail="Неподдерживаемый маркетплейс")
    
    # Проверяем, нет ли уже такого товара
    existing = db.query(TrackedProduct).filter(
        TrackedProduct.user_id == req.user_id,
        TrackedProduct.url == url
    ).first()
    
    if existing:
        return TrackResponse(
            status="exists",
            product_key=existing.product_key,
            marketplace=existing.marketplace,
            message="Товар уже отслеживается"
        )
    
    # Добавляем новый товар
    product = TrackedProduct(
        user_id=req.user_id,
        product_key=extract_product_key(url),
        url=url,
        marketplace=mp
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    
    # Фоновая задача: сразу проверить цену
    background_tasks.add_task(_fetch_initial_price, product.id)
    
    return TrackResponse(
        status="added",
        product_key=product.product_key,
        marketplace=mp,
        message=f"Товар добавлен, первая проверка в фоне"
    )


def _fetch_initial_price(product_id: int):
    """Фоновая задача: первичная проверка цены"""
    db = SessionLocal()
    try:
        product = db.query(TrackedProduct).get(product_id)
        if not product:
            return
        
        data = fetch_price(product.url, product.marketplace)
        if data and data.get("price"):
            product.current_price = data["price"]
            if data.get("title"):
                product.title = data["title"][:200]
            
            # Сохраняем в историю
            db.add(PriceHistory(
                product_key=product.product_key,
                price=data["price"],
                marketplace=product.marketplace,
                available=data.get("available", True)
            ))
            db.commit()
            logging.info(f"✅ Первичная проверка: {product.url[:50]}... = {data['price']} ₽")
    except Exception as e:
        logging.error(f"❌ Ошибка первичной проверки: {e}")
    finally:
        db.close()


@app.get("/products/{user_id}")
def get_products(user_id: int, db: Session = Depends(get_db)):
    """Получить список отслеживаемых товаров пользователя"""
    products = db.query(TrackedProduct).filter(
        TrackedProduct.user_id == user_id,
        TrackedProduct.is_active == True
    ).all()
    
    return [
        {
            "id": p.id,
            "marketplace": p.marketplace,
            "url": p.url,
            "title": p.title,
            "current_price": p.current_price,
            "created_at": p.created_at.isoformat() if p.created_at else None
        }
        for p in products
    ]


@app.post("/stop/{track_id}")
def stop_tracking(track_id: int, db: Session = Depends(get_db)):
    """Остановить отслеживание товара"""
    product = db.query(TrackedProduct).get(track_id)
    
    if not product:
        raise HTTPException(404, detail="Товар не найден")
    
    product.is_active = False
    db.commit()
    
    return {"status": "stopped", "id": track_id}


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def get_marketplace(url: str) -> str:
    """Определяет маркетплейс по ссылке (дублируется из bot.py для независимости)"""
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


# ===== ЗАПУСК =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)