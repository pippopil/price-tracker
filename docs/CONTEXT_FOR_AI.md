# 🤖 КОНТЕКСТ ПРОЕКТА ДЛЯ ИИ

## 🎯 Цель
Отслеживание цен на товары с Ozon, WB, Yandex Market, AliExpress. Уведомления через Telegram. Сравнение цен между площадками.

## 🧩 Архитектура
- Backend: Python 3.10+, FastAPI, SQLAlchemy (SQLite), APScheduler, aiogram
- Frontend: HTML/CSS/JS (vanilla), fetch API к `/track/`, `/products/`, `/stop/`
- DB: `backend/prices.db` (SQLite, таблицы: tracked_products, price_history)
- Bot: Telegram polling, команды /start, /list, /stop_all

## 📁 Ключевые файлы
- `backend/main.py` → REST API + запуск планировщика
- `backend/bot.py` → Обработка сообщений, запись в БД
- `backend/scheduler.py` → Фоновая проверка цен, отправка уведомлений
- `backend/scraper.py` → Заглушка `fetch_price_mock` (пока случайные цены)
- `frontend/index.html` + `script.js` → Ввод ссылки, отображение списка

## 🚀 Как запустить
1. `cd price-tracker`
2. `python -m venv venv` → активировать
3. `pip install -r backend/requirements.txt`
4. Окно 1: `cd backend && uvicorn main:app --reload --port 8000`
5. Окно 2: `cd backend && python bot.py`
6. Открыть `frontend/index.html`

## 📌 Текущий статус
- [✅] Бот работает на 100% через Cloudflare Worker + requests long-polling
- [✅] Все запросы к Bot API идут через telegram_request() (обход бага aiogram)
- [✅] Уведомления из scheduler.py тоже используют requests + Worker
- [ ] Реальный парсинг цен (заглушка fetch_price_mock)
- [ ] Деплой на бесплатный VPS

## 🔧 Архитектура бота
- Нет aiogram Dispatcher / start_polling()
- Простой цикл while True с requests.getUpdates()
- Обработка команд через функции: handle_start, handle_list, handle_link
