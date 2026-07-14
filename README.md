# HorseBio Insights

[![Deploy Backend](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-backend.yml/badge.svg)](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-backend.yml)
[![Deploy Frontend](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-frontend.yml/badge.svg)](https://github.com/AardSkelige/horsebio-insights/actions/workflows/deploy-frontend.yml)

Production business-analytics platform for a veterinary products company: MoySklad ERP synchronization, demand forecasting, purchase optimization, and marketplace analytics. Used daily by the purchasing team and management.

## Features

- **Demand forecasting** — Facebook Prophet on top of shipment history: monthly forecasts per product group with seasonality and trend awareness
- **ABC analysis** — products and counterparties categorized by revenue contribution (Pareto principle)
- **Purchase optimization** — reorder points calculated from demand forecasts, stock levels, and material lead times
- **Seasonality analysis** — detection of seasonal demand patterns per group and per SKU
- **Counterparty analytics** — customer behavior, groupings, shipment dynamics
- **Cash flow** — cash flow reporting built from ERP data
- **Ozon marketplace analytics** — API integration: sales, FBO stock, advertising campaigns
- **MoySklad automations** — background daemons (purchase price sync, returns monitoring, payment deadlines) and accounting integrity checks with findings acknowledged through the UI

## Architecture

```
MoySklad ERP ──┐
               ├──> sync (API parser) ──> PostgreSQL ──> forecasting / api ──> React SPA
Ozon API ──────┘                                              │
                                                    nginx (reverse proxy)
```

- **Backend** — Django 5 + Django REST Framework; domain apps: `sync` (MoySklad integration), `forecasting` (Prophet, ABC, seasonality, purchasing), `ozon` (marketplace), `api` (REST layer), `core` (domain models)
- **Frontend** — React 18 + Vite, Ant Design + Tailwind CSS, Recharts for charts; components organized by business domain (abc, purchases, seasonality, shipments, supplies, cash-flow, ozon-analytics)
- **Data** — PostgreSQL 17 in production, SQLite for local development; pandas/numpy for processing
- **Infrastructure** — Docker Compose, two nginx instances (frontend static + Django proxy), background process state persisted in named volumes

## CI/CD

GitHub Actions: every push to `main` runs the tests (backend against PostgreSQL 17, frontend with Vitest) and only after a green test stage builds Docker images, publishes them to GHCR, and deploys to the server over SSH. Secrets live exclusively in GitHub Secrets; configuration is environment-driven (`backend/.env.example`). A pre-commit hook with gitleaks guards against accidentally committed secrets.

## Quick Start

```bash
# Backend
cd backend
cp .env.example .env        # fill in the values
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8001

# Frontend
cd frontend
npm install
npm run dev                 # http://localhost:3001

# Or everything at once in Docker
docker-compose -f docker-compose.local.yml up --build
```

## Tests

```bash
cd backend && python manage.py test    # 150+ tests
cd frontend && npm test
```

## Notes

The project works with real company data, so the repository contains no fixtures or dumps: operational data comes from MoySklad during synchronization, and automation state lives in Docker volumes on the server.
