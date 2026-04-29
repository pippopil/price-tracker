"""
models.py — Модели базы данных
Таблицы: tracked_products, price_history
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./prices.db")

# Настройка движка БД
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TrackedProduct(Base):
    """Товары, которые отслеживает пользователь"""
    __tablename__ = "tracked_products"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)  # Telegram chat_id
    product_key = Column(String, index=True, nullable=False)  # Уникальный ключ товара
    url = Column(String, nullable=False)  # Ссылка на товар
    marketplace = Column(String, nullable=False)  # ozon, wildberries, yandex, aliexpress
    title = Column(String, nullable=True)  # Название товара (кэшируется)
    current_price = Column(Float, nullable=True)  # Последняя известная цена
    is_active = Column(Boolean, default=True, nullable=False)  # Включено ли отслеживание
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<TrackedProduct(id={self.id}, mp={self.marketplace}, price={self.current_price})>"


class PriceHistory(Base):
    """История изменения цен для аналитики"""
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    product_key = Column(String, index=True, nullable=False)  # Связь с TrackedProduct
    marketplace = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, default="RUB", nullable=False)
    available = Column(Boolean, default=True, nullable=False)  # Был ли товар в наличии
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<PriceHistory(key={self.product_key}, price={self.price}, ts={self.timestamp})>"


# Создаём таблицы при первом запуске
def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ База данных инициализирована")


if __name__ == "__main__":
    init_db()