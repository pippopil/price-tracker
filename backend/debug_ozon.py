"""
🔍 Отладочный скрипт: показывает ВСЁ, что можно найти на странице Ozon
Запусти: python debug_ozon.py
"""

import re
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

def get_headers():
    ua = UserAgent()
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

url = "https://www.ozon.ru/product/besprovodnye-naushniki-xiaomi-redmi-buds-4-lite-1146511155/"

print(f"🔍 Загружаем: {url}")
response = requests.get(url, headers=get_headers(), timeout=15)
html = response.text
soup = BeautifulSoup(html, 'lxml')

print("\n" + "="*60)
print("📋 ПОИСК ЦЕНЫ — все возможные места")
print("="*60)

# 1. Meta-теги (самый надёжный способ!)
print("\n🔹 Meta-теги:")
for meta in soup.find_all('meta', property=re.compile('product:price', re.I)):
    print(f"   {meta.get('property')}: {meta.get('content')}")

for meta in soup.find_all('meta', itemprop=re.compile('price', re.I)):
    print(f"   itemprop={meta.get('itemprop')}: {meta.get('content')}")

# 2. JSON-LD (структурированные данные — очень надёжно)
print("\n🔹 JSON-LD (структурированные данные):")
for script in soup.find_all('script', type='application/ld+json'):
    try:
        import json
        data = json.loads(script.string)
        # Рекурсивный поиск поля price
        def find_price(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.lower() == 'price' or k.lower() == 'pricecurrency':
                        print(f"   {path}.{k}: {v}")
                    find_price(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_price(item, f"{path}[{i}]")
        find_price(data)
    except:
        pass

# 3. Элементы с "price" в классе или data-атрибутах
print("\n🔹 Элементы с 'price' в селекторах:")
for tag in soup.find_all(class_=re.compile('price|cost', re.I)):
    text = tag.get_text(strip=True)[:100]
    if text:
        print(f"   class={tag.get('class')}: '{text}'")

for tag in soup.find_all(attrs={'data-testid': re.compile('price', re.I)}):
    text = tag.get_text(strip=True)[:100]
    if text:
        print(f"   data-testid={tag.get('data-testid')}: '{text}'")

# 4. Просто все теги с цифрами и ₽ (грубый поиск)
print("\n🔹 Грубый поиск: текст с '₽' и цифрами:")
for tag in soup.find_all(string=lambda text: text and '₽' in text and re.search(r'\d', text)):
    parent = tag.parent
    selector = f"{parent.name}"
    if parent.get('class'):
        selector += f".{parent['class'][0]}"
    if parent.get('id'):
        selector += f"#{parent['id']}"
    text = tag.strip()[:80]
    print(f"   {selector}: '{text}'")

print("\n" + "="*60)
print("💡 Скопируй найденный селектор и вставь в scraper.py")
print("="*60)