# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Argenprecios** is an async Python price-comparison platform for Argentine supermarkets. It scrapes product prices from retailers (Coto, ---, VTEX-based chains), stores them in MongoDB, and exposes a REST API + dashboard for price comparison.

## Setup & Running

```bash
# 1. Create env file
cp .env.example .env

# 2. Start MongoDB
docker-compose up -d mongo

# 3. Python environment
python -m venv .venv && pip install -r requirements.txt
playwright install chromium

# 4. Seed data (optional demo)
python scripts/seed_demo.py

# 5. Run the API
python main.py
```

Dashboard available at http://localhost:8000

## Common Commands

```bash
# Run all tests
python -m unittest test_parsers.py

# Run a single test
python -m unittest test_parsers.TestPriceParsing.test_clean_price

# Run with Docker (full stack)
docker-compose up -d

# Manual scraping trigger (API)
curl -X POST http://localhost:8000/clock/trigger

# Test a specific scraper
python scripts/test_scraper.py
```

## Architecture

Six modules with clear responsibilities:

| Module | Path | Role |
|--------|------|------|
| Clock | `modules/clock/scheduler.py` | APScheduler orchestrator — runs scraping at 6 AM + 12 PM (Argentina TZ), manages concurrency via semaphore, retries failures |
| Harvester | `modules/harvester/` | Playwright-based scrapers. `base_adapter.py` is the abstract base with anti-detection stealth, resource blocking, and delta upserts |
| PromoEngine | `modules/promo_engine/` | Regex/NLP parser for promotional text â†’ structured `ReglaDescuento`. Currently disabled in scheduler (Phase 2) |
| Brain | `modules/brain/` | Price comparison (`calculator.py`) and pre-aggregation for fast lookups (`sync.py`) |
| Operation | `modules/operation/` | Reserved for future POS/inventory features |
| Control | `modules/control/__init__.py` | All FastAPI routes |

## Adding a New Retailer Adapter

1. Create `modules/harvester/adapters/<name>_adapter.py` extending `BaseAdapter`
2. Implement `scrape_all()` and yield `ProductData` objects
3. Register the adapter in the scheduler's cadena loop in `modules/clock/scheduler.py`
4. Add the retailer config to MongoDB via `scripts/seed_comercios.py`

## Database Schema

MongoDB collections (all async via `motor`):

- **historial_precios** — Core price data, bucketed by `(ean, cadena_id)`, TTL 30 days
- **comercios_config** — Retailer on/off switch (`activo` field)
- **scraping_logs** — Per-run execution logs with per-cadena checkpoints
- **reglas_descuento** — Parsed promotions from PromoEngine
- **coto_mappings** — Maps Coto internal 8-digit IDs â†’ GTIN-13
- **config_usuario** — User wallet (cards + loyalty programs)
- **productos_vigentes** — Pre-aggregated for O(1) frontend lookups

Indexes are created at startup in `db/client.py`.

## Key Patterns

- **Concurrency**: `asyncio.Semaphore(MAX_CONCURRENT_BROWSERS / MAX_CONCURRENT_PAGES)` limits parallel browser instances. Controlled via `.env`.
- **Change detection**: Adapters only upsert when price data actually changed (`_has_changed()` in `base_adapter.py`).
- **EAN resolution**: Coto uses internal 8-digit IDs. `ean_utils.py` + `coto_mappings` collection handle GTIN-13 mapping.
- **Environment config**: All settings via `config/settings.py` (Pydantic BaseSettings). Never hardcode values.
- **VTEX adapters**: `vtex_master_adapter.py` is a single generic adapter for 9+ VTEX-based retailers, configured via `comercios_config`.

## Environment Variables

See `.env.example`. Key variables:
- `MAX_CONCURRENT_BROWSERS / MAX_CONCURRENT_PAGES` — parallel browser contexts (2–24 depending on hardware)
- `SCHEDULE_HOUR_1` / `SCHEDULE_HOUR_2` — scraping schedule in Argentina TZ
- `TTL_DAYS` — auto-deletion of old prices
- `API_KEY` — if set, enforces auth on POST endpoints


