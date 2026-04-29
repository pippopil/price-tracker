"""
scraper.py — Сбор цен с маркетплейсов

Архитектура:
- fetch_price(url, marketplace) → единая точка входа
- Возвращает: {"price": float, "title": str, "ean": str, "available": bool, "marketplace": str}
- При ошибке возвращает None → scheduler использует fallback

Поддерживаемые маркетплейсы:
- wildberries: парсинг JSON/HTML с обходом базовой защиты
- yandex: парсинг meta-тегов (надёжно)
- ozon: Playwright-парсер (комментирован, включай при необходимости)
- aliexpress: заглушка (расширяй по аналогии)
"""

import re
import time
import json
import logging
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# Глобальные настройки
REQUEST_TIMEOUT = 20  # секунд
REQUEST_DELAY = 2     # секунд между запросами (этикет)
MAX_RETRIES = 2       # попыток при ошибке

# Генератор реалистичных User-Agent
_ua = UserAgent()


def get_headers(referer: str = None) -> dict:
    """Возвращает заголовки, имитирующие реальный браузер"""
    headers = {
        "User-Agent": _ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _extract_price_from_text(text: str) -> float:
    """
    Извлекает число из текста цены.
    Примеры: "1 299 ₽" → 1299.0, "1,299.50" → 1299.5
    """
    if not text:
        return None
    # Убираем всё кроме цифр, точки, запятой
    cleaned = re.sub(r'[^\d.,]', '', str(text))
    cleaned = cleaned.replace(',', '.')
    try:
        price = float(cleaned)
        return round(price, 2) if price > 0 else None
    except (ValueError, TypeError):
        return None


def extract_product_key(url: str, html: str = "") -> str:
    """
    Извлекает уникальный идентификатор товара для сравнения между маркетплейсами.
    Приоритет: артикул из URL → EAN из meta-тегов → хэш от URL
    """
    # 1. Артикулы из URL (разные форматы)
    patterns = [
        r'ozon\.ru/product/[^-]+-(\d{5,})',  # Ozon: ...-12345/
        r'wildberries\.ru/catalog/(\d{7,})',  # WB: /catalog/12345678/
        r'market\.yandex\.ru/product/[^/]+/(\d+)',  # Yandex: /product/.../123/
        r'aliexpress\.ru/item/[^/]+/(\d{10,})',  # Ali: /item/.../1234567890.html
    ]
    for pattern in patterns:
        match = re.search(pattern, url, re.I)
        if match:
            mp = url.split('.')[1].split('/')[-1] if '.' in url else 'mp'
            return f"{mp}_{match.group(1)}"
    
    # 2. EAN/штрихкод из HTML (если передан)
    if html:
        ean_patterns = [
            r'<meta[^>]+property="product:retailer_item_id"[^>]+content="(\d+)"',
            r'<meta[^>]+name="gtin"[^>]+content="(\d{8,13})"',
            r'"ean"\s*:\s*"(\d{8,13})"',
        ]
        for pattern in ean_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                return f"ean_{match.group(1)}"
    
    # 3. Запасной вариант: хэш от URL
    return f"key_{abs(hash(url)) % 10**6}"


# =============================================================================
# ПАРСЕР WILDBERRIES (рабочий, с обходом защиты)
# =============================================================================
def _parse_wildberries(url: str) -> dict:
    """Парсит Wildberries с использованием сессий, куки и JSON-парсинга"""
    logging.info(f"🔍 WB: {url[:50]}...")
    
    for attempt in range(MAX_RETRIES):
        try:
            session = requests.Session()
            headers = get_headers("https://www.wildberries.ru/catalog")
            session.headers.update(headers)
            
            # "Прогрев" сессии
            session.get("https://www.wildberries.ru", timeout=10)
            time.sleep(1)
            
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            
            # Обработка блокировки 498
            if response.status_code == 498:
                logging.warning(f"⚠️ WB 498 (попытка {attempt+1}), меняем UA...")
                headers["User-Agent"] = _ua.random
                session.headers.update(headers)
                time.sleep(3)
                response = session.get(url, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                logging.error(f"❌ WB статус {response.status_code}")
                time.sleep(2)
                continue
            
            html = response.text
            time.sleep(REQUEST_DELAY)
            
            # === Способ 1: Парсинг JSON (надёжнее) ===
            json_patterns = [
                r'__initial-state__\s*=\s*({.+?});',
                r'data-page-data["\']?\s*:\s*({.+?})\s*[;,<]',
                r'window\.__preloadedData\s*=\s*({.+?});',
            ]
            
            for pattern in json_patterns:
                match = re.search(pattern, html, re.S | re.I)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        product = None
                        
                        # Навигация по структуре WB
                        if isinstance(data, dict):
                            for path in [['product'], ['data', 'product'], ['entities', 'product']]:
                                temp = data
                                for key in path:
                                    if isinstance(temp, dict) and key in temp:
                                        temp = temp[key]
                                    else:
                                        break
                                if isinstance(temp, dict) and 'priceU' in temp:
                                    product = temp
                                    break
                        
                        if product and 'priceU' in product:
                            price = product['priceU'] / 100  # WB хранит в копейках!
                            title = product.get('name', product.get('title', 'Товар WB'))
                            pid = product.get('id', extract_product_key(url))
                            
                            logging.info(f"✅ WB JSON: {title[:35]}... | {price} ₽")
                            return {
                                "price": round(price, 2),
                                "title": title,
                                "ean": f"wb_{pid}",
                                "available": product.get('inStock', True),
                                "marketplace": "wildberries"
                            }
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
            
            # === Способ 2: BeautifulSoup (запасной) ===
            soup = BeautifulSoup(html, 'lxml')
            price = None
            
            for selector in [
                {'class': re.compile(r'price__real|price-block__sum|price-unit', re.I)},
                {'data-qa': re.compile(r'price', re.I)},
                {'itemprop': 'price'},
            ]:
                tag = soup.find(**selector)
                if tag:
                    price = _extract_price_from_text(tag.get_text(strip=True))
                    if price:
                        break
            
            if price:
                title_tag = soup.find('h1', {'data-qa': 'product-name'})
                title = title_tag.get_text(strip=True) if title_tag else "Товар WB"
                logging.info(f"✅ WB HTML: {title[:35]}... | {price} ₽")
                return {
                    "price": round(price, 2),
                    "title": title,
                    "ean": extract_product_key(url, html),
                    "available": True,
                    "marketplace": "wildberries"
                }
            
            logging.warning(f"⚠️ WB: цена не найдена")
            return None
            
        except requests.RequestException as e:
            logging.error(f"❌ WB сетевая ошибка: {e}")
            time.sleep(3)
            continue
        except Exception as e:
            logging.error(f"❌ WB ошибка парсинга: {e}")
            return None
    
    return None


# =============================================================================
# ПАРСЕР YANDEX MARKET (простой, через meta-теги)
# =============================================================================
def _parse_yandex(url: str) -> dict:
    """Парсит Яндекс.Маркет через meta-теги (надёжно и просто)"""
    logging.info(f"🔍 Yandex: {url[:50]}...")
    
    try:
        headers = get_headers("https://market.yandex.ru/")
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        html = response.text
        time.sleep(REQUEST_DELAY)
        
        soup = BeautifulSoup(html, 'lxml')
        
        # 🎯 Meta-теги с ценой (самый надёжный способ)
        price = None
        for prop in ['product:price:amount', 'og:price:amount']:
            meta = soup.find('meta', property=prop)
            if meta and meta.get('content'):
                price = _extract_price_from_text(meta['content'])
                if price:
                    break
        
        if not price:
            meta = soup.find('meta', itemprop='price')
            if meta and meta.get('content'):
                price = _extract_price_from_text(meta['content'])
        
        if price:
            title = "Товар Яндекс"
            title_tag = soup.find('h1', {'data-zone-name': 'title'})
            if title_tag:
                title = title_tag.get_text(strip=True)
            
            ean = extract_product_key(url, html)
            logging.info(f"✅ Yandex: {title[:35]}... | {price} ₽")
            return {
                "price": round(price, 2),
                "title": title,
                "ean": ean,
                "available": True,
                "marketplace": "yandex"
            }
        
        logging.warning(f"⚠️ Yandex: цена не найдена в meta-тегах")
        return None
        
    except Exception as e:
        logging.error(f"❌ Yandex ошибка: {e}")
        return None


# =============================================================================
# ПАРСЕР OZON (Playwright-версия, раскомментируй при необходимости)
# =============================================================================
# Чтобы использовать, раскомментируй импорт в начале файла:
# from playwright.sync_api import sync_playwright
# from playwright_stealth import stealth_sync

def _parse_ozon(url: str) -> dict:
    """
    Парсер Ozon через Playwright (эмуляция браузера).
    ⚠️ Требует: pip install playwright playwright-stealth
    ⚠️ Запусти: playwright install chromium
    """
    logging.info(f"🔍 Ozon (Playwright): {url[:50]}...")
    
    try:
        # === ВАРИАНТ А: Прямой API (если известен эндпоинт) ===
        # Извлекаем ID товара из URL
        match = re.search(r'-(\d{5,})/?$', url)
        if match:
            product_id = match.group(1)
            # Попробуй известный эндпоинт (может устареть!)
            api_url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2/?url=/product/{product_id}/"
            try:
                resp = requests.get(api_url, headers=get_headers(url), timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    # Адаптируй под актуальную структуру ответа!
                    def find_price(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if k.lower() in ['price', 'currentprice'] and isinstance(v, (int, float)):
                                    return float(v) / 100
                                if isinstance(v, (dict, list)):
                                    r = find_price(v)
                                    if r: return r
                        elif isinstance(obj, list):
                            for item in obj:
                                r = find_price(item)
                                if r: return r
                        return None
                    price = find_price(data)
                    if price:
                        title = data.get('state', {}).get('product', {}).get('name', 'Товар Ozon')
                        return {
                            "price": round(price, 2),
                            "title": title,
                            "ean": f"ozon_{product_id}",
                            "available": True,
                            "marketplace": "ozon"
                        }
            except:
                pass  # Fallback к Playwright ниже
        
        # === ВАРИАНТ Б: Playwright (эмуляция браузера) ===
        # Раскомментируй этот блок, если API не работает:
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=get_headers()["User-Agent"],
                locale="ru-RU",
                timezone_id="Europe/Moscow"
            )
            page = context.new_page()
            stealth_sync(page)  # Скрывает признаки автоматизации
            
            page.goto(url, wait_until="networkidle", timeout=40000)
            page.wait_for_selector('[data-testid="price"], .Price', timeout=15000)
            
            title_elem = page.query_selector('h1[data-testid="item-name"]')
            title = title_elem.inner_text().strip() if title_elem else "Товар Ozon"
            
            price = None
            for sel in ['[data-testid="price-value"]', '[data-testid="price"]', '.Price']:
                elem = page.query_selector(sel)
                if elem:
                    price = _extract_price_from_text(elem.inner_text().strip())
                    if price: break
            
            browser.close()
            time.sleep(REQUEST_DELAY)
            
            if price:
                return {
                    "price": round(price, 2),
                    "title": title,
                    "ean": extract_product_key(url),
                    "available": "нет в наличии" not in page.content().lower(),
                    "marketplace": "ozon"
                }
        """
        
        logging.warning(f"⚠️ Ozon: цена не найдена (раскомментируй Playwright при необходимости)")
        return None
        
    except Exception as e:
        logging.error(f"❌ Ozon ошибка: {e}")
        return None


# =============================================================================
# ЗАГЛУШКА ALIEXPRESS (расширяй по аналогии)
# =============================================================================
def _parse_aliexpress(url: str) -> dict:
    """Заглушка для AliExpress — вернёт тестовые данные"""
    logging.info(f"🔍 AliExpress (заглушка): {url[:50]}...")
    time.sleep(REQUEST_DELAY)
    return {
        "price": 1200.00,
        "title": "Товар с AliExpress",
        "ean": extract_product_key(url),
        "available": True,
        "marketplace": "aliexpress"
    }


# =============================================================================
# ЕДИНАЯ ТОЧКА ВХОДА
# =============================================================================
def fetch_price(url: str, marketplace: str) -> dict:
    """
    Главная функция: принимает URL и маркетплейс, возвращает данные о товаре.
    
    Args:
        url: Ссылка на товар
        marketplace: ozon, wildberries, yandex, aliexpress
    
    Returns:
        dict с полями: price, title, ean, available, marketplace
        или None при ошибке
    """
    marketplace = marketplace.lower().strip()
    
    parsers = {
        "wildberries": _parse_wildberries,
        "yandex": _parse_yandex,
        "ozon": _parse_ozon,
        "aliexpress": _parse_aliexpress,
    }
    
    parser = parsers.get(marketplace)
    if not parser:
        logging.error(f"❌ Нет парсера для: {marketplace}")
        return None
    
    result = parser(url)
    
    # Fallback: если парсер вернул None, возвращаем заглушку (чтобы не ломать логику)
    if not result:
        logging.warning(f"⚠️ Fallback: заглушка для {marketplace}")
        return {
            "price": 1000.00,
            "title": f"Товар {marketplace}",
            "ean": extract_product_key(url),
            "available": True,
            "marketplace": marketplace
        }
    
    return result


# Обратная совместимость со старым кодом
fetch_price_mock = fetch_price