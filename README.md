# HorseBio Insights

[![Deploy Backend](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-backend.yml/badge.svg)](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-backend.yml)
[![Deploy Frontend](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-frontend.yml/badge.svg)](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-frontend.yml)

Производственная система бизнес-аналитики для компании в сфере ветеринарных препаратов: синхронизация с ERP МойСклад, прогнозирование спроса, оптимизация закупок и аналитика маркетплейсов. В ежедневной эксплуатации у команды закупок и руководства.

## Возможности

- **Прогнозирование спроса** — Facebook Prophet поверх истории отгрузок: помесячные прогнозы по товарным группам с учётом сезонности и трендов
- **ABC-анализ** — категоризация товаров и контрагентов по вкладу в выручку (принцип Парето)
- **Оптимизация закупок** — расчёт точек заказа по прогнозу спроса, остаткам и срокам поставки материалов
- **Сезонный анализ** — выявление сезонных паттернов спроса по группам и отдельным позициям
- **Анализ контрагентов** — поведение клиентов, группировки, динамика отгрузок
- **Cash flow** — отчёт о движении денежных средств по данным ERP
- **Аналитика Ozon** — интеграция с API маркетплейса: продажи, FBO-остатки, рекламные кампании
- **Автоматизации МойСклад** — фоновые демоны (синхронизация закупочных цен, контроль возвратов, дедлайны оплат) и проверки целостности учёта с подтверждением находок через UI

## Архитектура

```
МойСклад ERP ──┐
               ├──> sync (парсер API) ──> PostgreSQL ──> forecasting / api ──> React SPA
Ozon API ──────┘                                              │
                                                    nginx (reverse proxy)
```

- **Backend** — Django 5 + Django REST Framework; доменные приложения: `sync` (интеграция МойСклад), `forecasting` (Prophet, ABC, сезонность, закупки), `ozon` (маркетплейс), `api` (REST-слой), `core` (доменные модели)
- **Frontend** — React 18 + Vite, Ant Design + Tailwind CSS, графики на Recharts; компоненты организованы по бизнес-доменам (abc, purchases, seasonality, shipments, supplies, cash-flow, ozon-analytics)
- **Данные** — PostgreSQL 17 на проде, SQLite для локальной разработки; pandas/numpy для обработки
- **Инфраструктура** — Docker Compose, два nginx (статика фронта + прокси к Django), состояние фоновых процессов в именованных volume

## CI/CD

GitHub Actions: пуш в `main` прогоняет тесты (backend — против PostgreSQL 17, frontend — Vitest) и только после зелёных тестов собирает Docker-образы, публикует их в GHCR и выкатывает на сервер по SSH. Секреты — только в GitHub Secrets, конфигурация — через переменные окружения (`backend/.env.example`). Pre-commit хук с gitleaks защищает от случайного коммита секретов.

## Быстрый старт

```bash
# Backend
cd backend
cp .env.example .env        # заполнить значения
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8001

# Frontend
cd frontend
npm install
npm run dev                 # http://localhost:3001

# Либо всё сразу в Docker
docker-compose -f docker-compose.local.yml up --build
```

## Тесты

```bash
cd backend && python manage.py test    # 150+ тестов
cd frontend && npm test
```

## Примечания

Проект работает с реальными данными компании, поэтому в репозитории нет фикстур и дампов: рабочие данные приходят из МойСклад при синхронизации, состояние автоматизаций живёт в Docker volume на сервере.
