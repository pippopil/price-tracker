import re
from rapidfuzz import fuzz
from typing import Dict, Optional

# ВНИМАНИЕ: В продакшене замените на официальные API или легализованный парсинг.
# Эта заглушка имитирует ответ для демонстрации архитектуры.

def extract_product_key(url: str, title: str = "") -> str:
    """Извлекает EAN/артикул или создаёт хэш из названия"""
    ean_match = re.search(r'\d{8,13}', url or title)
    if ean_match:
        return ean_match.group(0)
    return f"key_{hash(title.lower().strip()) % 10**6}"

def normalize_title(title: str) -> str:
    return re.sub(r'\s+', ' ', title.lower().strip())

def fetch_price_mock(url: str, marketplace: str) -> Dict:
    """Имитация парсера. Замените на реальный запрос к API/HTML"""
    import random
    base_prices = {"ozon": 1500.0, "wildberries": 1450.0, "yandex": 1600.0, "aliexpress": 1200.0}
    price = base_prices.get(marketplace.lower(), 1000.0)
    # Имитация изменения цены
    price = round(price + random.uniform(-50, 50), 2)
    return {
        "price": price,
        "title": f"Тестовый товар {marketplace}",
        "ean": extract_product_key(url, f"Тестовый товар {marketplace}")
    }

def find_best_price(product_key: str, db_session) -> Optional[Dict]:
    """Находит минимальную цену по product_key"""
    from models import PriceHistory
    latest = {}
    for ph in db_session.query(PriceHistory).filter(PriceHistory.product_key == product_key).all():
        if ph.marketplace not in latest or ph.price < latest[ph.marketplace]["price"]:
            latest[ph.marketplace] = {"price": ph.price, "timestamp": ph.timestamp}
    if not latest:
        return None
    best_mp = min(latest, key=lambda m: latest[m]["price"])
    return {"marketplace": best_mp, "price": latest[best_mp]["price"]}