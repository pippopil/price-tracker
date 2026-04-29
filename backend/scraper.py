import re
import random

def extract_product_key(url: str) -> str:
    ean = re.search(r'\d{8,13}', url or "")
    return ean.group(0) if ean else f"key_{hash(url) % 1000000}"

def fetch_price_mock(url: str, marketplace: str) -> dict:
    base = {"ozon": 1500, "wildberries": 1450, "yandex": 1600, "aliexpress": 1200}
    price = base.get(marketplace.lower(), 1000) + random.uniform(-50, 50)
    return {"price": round(price, 2), "title": f"Товар {marketplace}", "ean": extract_product_key(url)}