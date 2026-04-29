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
- [✅] Работает локально
- [✅] Добавление через сайт и бот
- [✅] Уведомления каждые 10 мин (заглушка)
- [ ] Реальный парсинг цен
- [ ] Переход на PostgreSQL + Celery
- [ ] Деплой на VPS

## 🛠️ Задачи на следующий чат
(заполни сюда, что нужно сделать дальше)