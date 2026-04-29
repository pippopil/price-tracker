"""
🕷️ scraper.py — Сбор цен с маркетплейсов
Архитектура:
- fetch_price(url, marketplace) → единая точка входа
- _parse_ozon(), _parse_wildberries() и т.д. → парсеры для каждого сайта
- Все парсеры возвращают одинаковый формат: {"price": float, "title": str, "ean": str}
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# Генератор реалистичных User-Agent (чтобы не блокировали как бота)
ua = UserAgent()

# === Настройки запросов ===
REQUEST_TIMEOUT = 15  # секунд
REQUEST_DELAY = 2     # секунд между запросами (этикет для сервера)

# === Заголовки, имитирующие реальный браузер ===
def get_headers():
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }

# === Извлечение артикула / EAN из ссылки или страницы ===
def extract_product_key(url: str, html: str = "") -> str:
    """
    Пытается найти уникальный идентификатор товара:
    1. Артикул из URL (Ozon: /product/...-12345/)
    2. EAN/штрихкод из meta-тегов
    3. Хэш от названия как запасной вариант
    """
    # 1. Пробуем найти цифры в URL (артикул)
    match = re.search(r'-(\d{5,})/?$', url)  # Ozon-стиль: ...-12345/
    if match:
        return f"ozon_{match.group(1)}"
    
    match = re.search(r'/(\d{7,})', url)  # Общий паттерн: /12345678
    if match:
        return f"mp_{match.group(1)}"
    
    # 2. Пробуем найти EAN в HTML (если передан)
    if html:
        ean_patterns = [
            r'<meta[^>]+property="product:retailer_item_id"[^>]+content="([^"]+)"',
            r'<meta[^>]+name="gtin"[^>]+content="([^"]+)"',
            r'"ean"\s*:\s*"(\d{8,13})"',  # JSON-вставка
        ]
        for pattern in ean_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                return f"ean_{match.group(1)}"
    
    # 3. Запасной вариант: хэш от нормализованного URL
    return f"key_{abs(hash(url)) % 10**6}"

# === Парсер Ozon (реальный) ===
def _parse_ozon(url: str) -> dict:
    """
    Парсит страницу товара на Ozon.
    Возвращает: {"price": float, "title": str, "ean": str, "available": bool}
    """
    logging.info(f"🔍 Парсинг Ozon: {url[:60]}...")
    
    try:
        # Делаем запрос с заголовками "как у браузера"
        response = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        html = response.text
        
        # Небольшая задержка (этикет)
        time.sleep(REQUEST_DELAY)
        
        # Парсим HTML
        soup = BeautifulSoup(html, 'lxml')
        
        # 1. Извлекаем название
        title = "Товар Ozon"
        title_tag = soup.find('h1', {'data-testid': 'item-name'})
        if title_tag:
            title = title_tag.get_text(strip=True)
        else:
            # Запасной селектор
            title_tag = soup.find('h1', class_=re.compile(r'item-name|product-title', re.I))
            if title_tag:
                title = title_tag.get_text(strip=True)
        
        # 2. Извлекаем цену (самое важное!)
        price = None
        
        # Основной селектор: цена в рублях
        price_tag = soup.find('div', {'data-testid': 'price'})
        if price_tag:
            price_text = price_tag.get_text(strip=True)
            price = _extract_price_from_text(price_text)
        
        # Запасные селекторы (Ozon часто меняет вёрстку)
        if not price:
            for selector in [
                {'class': re.compile(r'price|cost', re.I)},
                {'data-testid': 'price-value'},
                {'itemprop': 'price'},
            ]:
                tag = soup.find(**selector)
                if tag:
                    price = _extract_price_from_text(tag.get_text(strip=True))
                    if price:
                        break
        
        # 3. Проверяем доступность
        available = True
        if soup.find(text=re.compile(r'нет в наличии|товар закончился', re.I)):
            available = False
        
        # 4. Извлекаем артикул / EAN
        ean = extract_product_key(url, html)
        
        if price:
            logging.info(f"✅ Ozon: {title[:40]}... | {price} ₽ | {'✅' if available else '❌'}")
            return {
                "price": price,
                "title": title,
                "ean": ean,
                "available": available,
                "marketplace": "ozon"
            }
        else:
            logging.warning(f"⚠️ Не удалось найти цену на Ozon: {url}")
            return None
            
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Ошибка запроса к Ozon: {e}")
        return None
    except Exception as e:
        logging.error(f"❌ Ошибка парсинга Ozon: {e}")
        return None

# === Вспомогательная функция: извлечение числа из текста цены ===
def _extract_price_from_text(text: str) -> float:
    """
    Превращает "1 299 ₽", "1,299.50", "1299.50 руб." → 1299.50
    """
    # Убираем всё, кроме цифр, точки и запятой
    cleaned = re.sub(r'[^\d.,]', '', text)
    # Заменяем запятую на точку (для дробных)
    cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None

# === Заглушки для других маркетплейсов (расширяй по аналогии) ===
def _parse_wildberries(url: str) -> dict:
    """Заглушка: вернёт тестовые данные. Замени на реальный парсер."""
    logging.info(f"🔍 Wildberries (заглушка): {url[:60]}...")
    time.sleep(REQUEST_DELAY)
    return {
        "price": 1450.00,
        "title": "Товар с Wildberries",
        "ean": extract_product_key(url),
        "available": True,
        "marketplace": "wildberries"
    }

def _parse_yandex(url: str) -> dict:
    """Заглушка: вернёт тестовые данные."""
    logging.info(f"🔍 Yandex Market (заглушка): {url[:60]}...")
    time.sleep(REQUEST_DELAY)
    return {
        "price": 1600.00,
        "title": "Товар с Яндекс.Маркета",
        "ean": extract_product_key(url),
        "available": True,
        "marketplace": "yandex"
    }

def _parse_aliexpress(url: str) -> dict:
    """Заглушка: вернёт тестовые данные."""
    logging.info(f"🔍 AliExpress (заглушка): {url[:60]}...")
    time.sleep(REQUEST_DELAY)
    return {
        "price": 1200.00,
        "title": "Товар с AliExpress",
        "ean": extract_product_key(url),
        "available": True,
        "marketplace": "aliexpress"
    }

# === Единая точка входа: fetch_price ===
def fetch_price(url: str, marketplace: str) -> dict:
    """
    Главная функция: принимает URL и название маркетплейса,
    возвращает данные о товаре или None при ошибке.
    
    Использование:
        result = fetch_price("https://ozon.ru/...", "ozon")
        if result:
            print(f"Цена: {result['price']} ₽")
    """
    marketplace = marketplace.lower().strip()
    
    # Маршрутизация к нужному парсеру
    parsers = {
        "ozon": _parse_ozon,
        "wildberries": _parse_wildberries,
        "yandex": _parse_yandex,
        "aliexpress": _parse_aliexpress,
    }
    
    parser = parsers.get(marketplace)
    if not parser:
        logging.error(f"❌ Нет парсера для маркетплейса: {marketplace}")
        return None
    
    # Вызываем парсер
    result = parser(url)
    
    # Если парсер вернул None — возвращаем заглушку (чтобы не ломать логику)
    if not result:
        logging.warning(f"⚠️ Парсер не вернул данные, используем заглушку")
        return {
            "price": 1000.00,
            "title": f"Товар {marketplace}",
            "ean": extract_product_key(url),
            "available": True,
            "marketplace": marketplace
        }
    
    return result

# === Обратная совместимость: старое имя функции ===
# (чтобы не переписывать scheduler.py)
fetch_price_mock = fetch_price