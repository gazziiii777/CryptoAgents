# TradingAgents — статус (снапшот)

Живой снапшот «где мы». Полный план — [architecture-mvp.md](architecture-mvp.md), полная арка — [architecture-roadmap.md](architecture-roadmap.md).
Обновлено: 2026-05-27.

---

## ✅ Сделано

### Iter 1 — Persistence (фундамент)
- MariaDB + SQLModel: модели (`Account`, `Signal`, `VirtualPosition`, `Event`, `SystemState`) + репозитории.
- Alembic init + миграции (драйвер `aiomysql`).
- `Decimal` через TypeDecorator (`NUMERIC(28,10)` в MariaDB), `UTCDateTime` (reject naive).
- MariaDB 11 (utf8mb4), пул соединений (`DB_POOL_*`).
- `core/settings.py` с валидаторами (`Field(ge/le)`) на все константы.
- Тесты слоя БД (`tests/unit/db/`: constraints, repositories, types).
- **Остатки Iter 1 (не блокируют Iter 2):** daily backup (константы есть, кода нет) · CLI `equity-curve` · data-quality monitors.

### Pipeline до аналитиков
- **Universe** — ликвидные perp Binance ≥ $5M/24h.
- **Screener** — ADX-gate + 15-критериальный score + vote-based direction (`evaluation`, `indicators`, `criteria`, `universe`).
- **Enricher** — batch macro + per-symbol LunarCrush → `EnrichedCandidate` (`enricher`, `insight`).
- **Data-клиенты** — ccxt, binance, coinglass, coingecko, lunarcrush (все на Pydantic `model_validate`).

### LLM-инфра (фундамент Iter 2)
- `app/clients/llm/` — `LLMClient` (litellm + instructor, structured output → Pydantic, `(parsed, LLMUsage)`).
- `app/llm_gateway/` — `LLMService.structured()` (budget gate → вызов → `Event(llm_call)`), `DailyBudgetGuard` (UTC-дневной cap), `LLMBudgetExceededError`.
- Report-модели 4-агентной схемы уже описаны в `app/analysts/models.py`.

### Quality-фундамент (эта сессия)
- **mypy** — прагматичный конфиг, `app/core/db` зелёные (70 файлов).
- **Тесты** — `tests/unit/` + `tests/integration/` (опт-ин по маркеру). Покрыта чистая логика: insight, criteria, screener model-parsing, budget guard (freezegun), indicators. 50 тестов.
- **Makefile** — `install / lint / format / typecheck / test / test.cov / test.integration / check / clean` (локальный uv, без docker).
- **CI** — `.github/workflows/ci.yml`: push в main + PR → `make check`.
- **Coverage** — source app/core/db, `fail_under` = 40 (ratchet-baseline при текущих ~42%; растить по мере добавления интеграционных тестов).

---

## 🔜 Дальше — Iter 2: LLM-аналитики + агрегатор

**Схема (осознанный отход от MVP-дока):** полная 4-агентная — Macro / Derivatives / Technical (LangGraph с tools) / Sentiment раздельно, не 3 merged.

### Подготовка перед аналитиками (короткое, разблокирующее)
1. ✅ **`langgraph` поднят в `[project.dependencies]`** + `pyyaml`. `langchain-anthropic` оставлен в dev — LLM-вызовы внутри нод идут через `LLMService` (litellm+instructor, cost-tracking), а не через langchain-модель.
2. ✅ **Графы через config.yaml**, не langgraph.json: `app/agents/graph_builder.build_graph(config, state_schema, nodes, conditions)` собирает `StateGraph` из декларативной топологии (`app/agents/models.py`: `GraphConfig`/`EdgeConfig`) с fail-fast валидацией ссылок. langgraph как библиотека (in-process `invoke`), без сервера/Studio.
3. 🔲 **Тест `LLMService.structured`** (с замоканным `LLMClient`) — фундамент, на котором строятся все аналитики, сейчас 0% покрытия.
4. 🔲 **Mock-инфраструктура данных** — mock-клиенты / mock-режим enricher для end-to-end тестов аналитиков без расхода API-квоты. Заодно убирает фабрикацию данных в CLI (`enrich --mock` сейчас собирает `EnrichmentResult` в транспортном слое).
5. 🔲 **`ANTHROPIC_API_KEY` в `.env`** — прекондишн, чтобы реально прогнать (acceptance Iter 2). Завести `.env.example`.

### Сами аналитики
- 🔲 MacroAnalyst → `MacroReport`
- 🔲 DerivativesAnalyst → `DerivativesReport`
- 🔲 TechnicalAnalyst (LangGraph-граф с tools) → `TechnicalReport` (граф собирается через `build_graph` из `app/agents/technical/graph.yaml` + реестр нод/условий)
- 🔲 SentimentAnalyst → `SentimentReport`
- 🔲 SignalAggregator → `SignalSynthesis` с `confluence_score`

**Acceptance:** для одного кандидата screener'а получить `SignalSynthesis` с осмысленным `confluence_score` и breakdown по аналитикам; LLM-cost залогирован в `Event`.

### Дальнейшие итерации (по MVP-доку)
- **Iter 3** — SetupIntent (LangGraph) + LevelComputer (Python, числа) + RiskValidator.
- **Iter 4** — PortfolioManager (4 pre-trade checks) + Position Watcher + restart recovery.
- **Iter 5** — Telegram + scheduler + delisting check + equity curve + E2E.

### Долг качества (не блокирует, растить параллельно)
- Поднять coverage 40 → 75: интеграционные тесты клиентов (respx) + пайплайна (на mock-инфре).
- Опционально: pre-commit (локальный двойник CI), README с `make`-командами.

---

## ✂️ Отсечено потому что MVP

Полная таблица — в `architecture-mvp.md` (раздел «Что НЕ в MVP»). Заголовки:

- **Аналитика/agents:** OnChainAnalyst, DevilsAdvocate, ConflictResolver, Bull/Bear debate subgraph.
- **Persistence:** EquitySnapshot daily, MarketDataPIT bitemporal, event-log archival (4 таблицы вместо 6).
- **Setup-движок:** 3 setup-типа (не 6), 5 entry / 3 stop / 3 target references (урезано), один target без T1/T2 partials, без confluence_zone / OB / FVG / volume profile, один fixed stop (без trailing).
- **Риск:** fixed 1% NAV (не Kelly), один DD-уровень −10% (не 3), без daily PnL stop, без vol-target, max 2 long + 2 short (без correlation matrix).
- **Валидация/метрики:** без DSR/PSR, walk-forward CV, model-drift detection, HMM regime detector, macro blackout calendar (вместо него — ручной `halt-trading`).
- **Ops:** cron вместо APScheduler-persistence, один account, strategy version = semver (без IC-hash).

**Важно — это НЕ упрощаем (quality bar = prod):** Decimal для денег, UTC-aware datetime, миграции MariaDB (Alembic), idempotency (unique `Signal(symbol, bar_close_ts)`), restart recovery, settings-валидация, log sanitization, тесты на critical paths, LLM cost tracking + budget cap, «LLM никогда не пишет торговые числа» (SetupIntent → LevelComputer).

**Сознательное расширение сверх MVP:** 4 раздельных аналитика вместо 3 merged (см. решение в `architecture-mvp.md` § Iter 2).
