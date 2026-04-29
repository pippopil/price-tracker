from scraper import fetch_price

# Замени на реальную ссылку с работающим товаром
test_url = "https://www.wildberries.ru/catalog/220745754/detail.aspx?targetUrl=SN"

print("🔍 Тестируем парсер Wildberries...")
result = fetch_price(test_url, "wildberries")

if result and result['price'] != 1000.0:  # 1000.0 = заглушка
    print(f"✅ Успех!")
    print(f"   Название: {result['title'][:60]}...")
    print(f"   Цена: {result['price']} ₽")
    print(f"   Артикул: {result['ean']}")
else:
    print("❌ Не удалось получить реальную цену")