from scraper import fetch_price

# Тестовая ссылка на Ozon (замени на реальную, если есть)
test_url = "https://www.ozon.ru/product/kurtka-semybear-vetrovka-real-madrid-vetrovka-real-madrid-adidas-vetrovka-adidas-2062839583/?at=r2t4z4X2OujRXPDlTRylDqASy96R1QcEXX1LzC0KQYWk"

print("🔍 Тестируем парсер Ozon...")
result = fetch_price(test_url, "ozon")

if result:
    print(f"✅ Успех!")
    print(f"   Название: {result['title'][:60]}...")
    print(f"   Цена: {result['price']} ₽")
    print(f"   Артикул: {result['ean']}")
    print(f"   В наличии: {'✅' if result['available'] else '❌'}")
else:
    print("❌ Не удалось получить данные")