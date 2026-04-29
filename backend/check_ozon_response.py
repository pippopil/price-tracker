"""
🔍 Проверяем, что возвращает Ozon на наш запрос
"""
import requests
from fake_useragent import UserAgent

def get_headers():
    ua = UserAgent()
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://www.google.com/",  # Притворяемся, что пришли из поиска
    }

url = "https://www.ozon.ru/product/besprovodnye-naushniki-xiaomi-redmi-buds-4-lite-1146511155/"

print(f"🔍 Запрашиваем: {url}")
response = requests.get(url, headers=get_headers(), timeout=15)

print(f"\n📊 Статус: {response.status_code}")
print(f"📦 Размер ответа: {len(response.text)} байт")
print(f"🔖 Заголовки ответа: {dict(response.headers)}")

# Сохраняем ответ в файл для изучения
with open("ozon_response.html", "w", encoding="utf-8") as f:
    f.write(response.text)

print(f"\n💾 Ответ сохранён в ozon_response.html")

# Проверяем на признаки блокировки
html = response.text.lower()
if "captcha" in html or "access denied" in html or "проверка" in html:
    print("\n🚨 ВНИМАНИЕ: Обнаружена капча или блокировка!")
elif len(response.text) < 5000:
    print("\n⚠️ Подозрительно короткий ответ — возможно, это не страница товара")
else:
    print("\n✅ Ответ выглядит как нормальная страница")