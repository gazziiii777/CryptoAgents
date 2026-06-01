# Архитектура TradingAgents

Многоагентная система для свинг-трейдинга крипто-перпетуалов на 4h-таймфрейме.
Пейпер-трейдинг (виртуальные позиции) с полной записью контекста решений для
последующего исследования и калибровки.

Цикл: каждые 4 часа (закрытие бара) система отбирает ликвидные пары, обогащает их
деривативными/социальными данными, прогоняет через 4 LLM-аналитиков + дебаты
bull/bear/trader, детерминированно считает уровни и риск, открывает/закрывает
виртуальные позиции и шлёт уведомления в Telegram.

---

## 1. Высокоуровневый поток

```
                          ┌─────────────────────────────────────────────┐
                          │  Scheduler (app/scheduler.py)                 │
                          │  каждые 4h: watcher tick → pipeline           │
                          └───────────────┬───────────────────────────────┘
                                          │
              ┌───────────────────────────┴────────────────────────────┐
              ▼                                                          ▼
   ┌──────────────────────┐                            ┌────────────────────────────────┐
   │ PositionWatcher      │                            │ Pipeline (app/pipeline/runner) │
   │ реконсиляция OPEN,   │                            └───────────────┬────────────────┘
   │ выходы, PnL, equity  │                                            │
   └──────────┬───────────┘         ┌──────────────┬──────────────┬────┴────────┬──────────────┐
              │                     ▼              ▼              ▼             ▼              ▼
   ┌──────────▼─────────┐   ┌────────────┐  ┌────────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐
   │ research: outcome  │   │ Screener   │→ │ Enricher   │→ │ Analysis │→ │ Persist   │→ │ Research │
   │ Telegram: closed   │   │ universe→  │  │ LunarCrush │  │ 4 агента │  │ Signal +  │  │ writer   │
   └────────────────────┘   │ gate+score │  │ +macro+f&g │  │ +дебаты  │  │ PM откр.  │  │ snapshot │
                            └────────────┘  └────────────┘  └──────────┘  └─────┬─────┘  └──────────┘
                                                                                │
                                                                   Telegram: opened
```

Стадии (`app/pipeline/runner.py::run_pipeline`):
**screener → enricher → analysis → persist → research-write**. Каждая стадия логирует
итоговый JSON в поле `result`.

---

## 2. Точки входа и запуск

| Вход | Назначение |
|---|---|
| `cli/` (Typer) | CLI: `run` (scheduler loop / `--once`), `watch`, `pipeline`, `manage`, `keys_check` |
| `cli/commands/run.py` | `preflight()` → `run_forever()` или `run_once()` из `app/scheduler.py` |
| `main.py` | Одноразовый прогон pipeline + предупреждение о устаревшей калибровке |
| `app/scheduler.py` | Цикл по 4h-барам: `seconds_until_next_tick`, мягкая остановка по SIGTERM/SIGINT, dispose engine'ов |

Прод запускается как Docker-сервис `worker` (`docker compose`), `run_forever` —
немедленный первый тик при старте, дальше по закрытию каждого 4h-бара.

---

## 3. Слои и пакеты

| Пакет | Ответственность |
|---|---|
| `app/screener/` | Отбор ликвидных перпов, технический gate + scoring |
| `app/enricher/` | Обогащение соц-данными (LunarCrush) + макро (CoinGecko) + fear&greed |
| `app/analysts/` | LLM-аналитики: macro, derivatives, sentiment + дебаты (bull/bear/trader), devil's advocate |
| `app/agents/` | LangGraph-агенты: `technical` (TA-факты), `setup` (SetupIntent). Generic `graph_builder` + `graph.yaml` |
| `app/aggregator.py` | Детерминированная свёртка 4 отчётов во взвешенное голосование (`SignalSynthesis`) |
| `app/levelcomputer.py` | SetupIntent → реальные цены (`CryptoSetup`); вход по market, ATR-стоп ≤8%, потолок цели 20% |
| `app/riskvalidator.py` | Проверка R:R и санити сетапа |
| `app/portfolio/` | Pre-trade gates, сайзинг, плечо, открытие/закрытие позиций, PnL, watcher |
| `app/pipeline/` | Оркестрация: `runner` (стадии), `analysis` (по кандидату), `persistence` (Signal+PM) |
| `app/clients/` | Внешние API: ccxt, binance, coinglass, coingecko, lunarcrush, llm, telegram |
| `app/llm_gateway/` | Обёртка LLM: бюджет-гейт, cost-tracking поверх `app/clients/llm` |
| `app/notifications/` | Telegram-уведомления об открытии/закрытии позиций (aiogram) |
| `app/models/` | Cross-feature Pydantic-контракты (analysis, enricher, screener, setup) |
| `core/` | settings, constants, prompts (yaml + loader), symbols |
| `db/` | Торговая БД (MariaDB): engine, models, repositories |
| `db/research/` | Исследовательская БД: signal_record, agent_output, trade_outcome (create_all) |
| `scripts/research/` | Офлайн-аналитика: attribution, calibrate, analyze, collect_data |

**Слоевая дисциплина:** транспорт (clients) ← бизнес-логика (pipeline/analysts/portfolio)
← данные (db/repositories). Деньги и риск **полностью детерминированы** (Python), LLM не
пишет числа — только категории/направления.

---

## 4. Конвейер по стадиям

### 4.1 Screener (`app/screener/`)
- `universe.py` — ликвидные перпы биржи (swap + USDT + active + COIN + объём ≥ `UNIVERSE_MIN_VOLUME_USD`), сортировка по объёму.
- `screener.py` — параллельная оценка (семафор `SCREENER_CONCURRENCY`) через `evaluation.py::evaluate_symbol`, клиенты ccxt/binance/coinglass.
- `criteria.py` + `indicators.py` — технический gate (ADX и др.) и scoring; деривативные сигналы (funding, OI, L/S, CVD, smart-money divergence).
- Фильтр: `gate_passed AND score ≥ SCREENER_MIN_SCORE`, топ-N по score → `ScreenerResult[]`.

### 4.2 Enricher (`app/enricher/`)
- На батч: CoinGecko макро-снимок + CoinGlass fear&greed + LunarCrush topic-metrics.
- На символ (параллельно): LunarCrush news / posts / time_series / ai-context / whatsup.
- `insight.py::derive_social_insight` — attention_level, retail-vs-influencer, pump_risk.
- Результат: `EnrichmentResult{candidates: EnrichedCandidate[], macro, fear_greed}`.

### 4.3 Analysis (`app/pipeline/analysis.py`)
Macro считается **один раз на прогон**. По каждому кандидату:
1. `analyze_derivatives` + `analyze_sentiment` (LLM, quick-модель).
2. Фетч 4h/1d свечей → `analyze_technical` (LangGraph-агент → `TechnicalReport`).
3. `aggregate_signals` → `SignalSynthesis` (взвешенное голосование).
4. Если bias ≠ Neutral → **дебаты** (`run_debate`): bull + bear (параллельно, quick) → trader (deep) → `apply_trader_verdict`.
5. **Setup-цепочка** (`_run_setup_chain`): гейт по confluence → `build_setup` (LangGraph → `SetupIntent`) → `resolve_setup` (LevelComputer) → `validate_risk` → `run_devils_advocate` (red-team veto, корректирует confluence) → `format_signal` (`FinalSignal`).

### 4.4 Persist (`app/pipeline/persistence.py`)
- Кандидаты сортируются по `analyst_confluence` убыванием — лучшие забирают слоты первыми.
- На каждый: `Signal` (idempotent по symbol+bar) + `Event(SIGNAL_GENERATED, snapshot)` + при signal_ready — `PortfolioManager.evaluate` выносит реальный Decision.

### 4.5 Research-write (`db/research/writer.py`)
- `signal_record` (полный контекст решения) + 4× `agent_output` на каждый сигнал.
- Изолировано: сбой записи логируется, **не ломает торговлю**.

---

## 5. Многоагентная аналитика

```
   macro ─┐
deriv ────┼─► aggregate_signals ─► SignalSynthesis ─► [bias≠Neutral] ─► bull ─┐
sent  ────┤   (weighted vote)         (confluence)                    bear ─┼─► trader
tech ─────┘                                                                  │   (verdict +
                                                                             │    conviction)
                                                                             ▼
                                              apply_trader_verdict ─► setup chain ─► Devil's Advocate
```

- **Веса голосования** (`app/aggregator.py`): macro 0.20, derivatives 0.25, sentiment 0.20, technical 0.35; порог bias ±0.15.
- `confluence_score = |weighted_sum| × CONFIDENCE_SHRINKAGE`; **`analyst_confluence`** сохраняет сырое аггрегаторное значение (для сайзинга/ранжирования — трейдер его не затирает).
- **Trader** — финальный решающий: его направление становится `overall_bias`, conviction × shrinkage → confluence; при расхождении с голосованием — доп. штраф ×0.5.
- **Модели LLM**: quick = `gpt-4o-mini` (аналитики, исследователи), deep = `gpt-4o` (trader). Конфиг в `core/constants/llm.py`.
- **Промпты** — `core/prompts/*.yaml`, грузятся через `core/prompts/loader.py`.

---

## 6. Детерминированный риск-слой (`app/portfolio/`, `app/levelcomputer.py`)

Числа считает Python, не LLM:
- `levelcomputer.resolve_setup` — вход **по market** (current_price), стоп = ATR×mult в `[0.3%, 8%]`, цель ≤ **20%** дистанции, иначе clamp; R:R пересчитывается.
- `PortfolioManager` (`manager.py`) — 4 pre-trade gate: drawdown-breaker → slot (`MAX_CONCURRENT_POSITIONS`) → same-direction (`MAX_SAME_DIRECTION`) → funding kill-switch; + dedup по символу.
- `sizing.py` — фикс-фракционный риск: `confidence_risk_pct(analyst_confluence, ...)` интерполирует risk_pct в `[MIN, MAX]`; `compute_qty = NAV×risk_pct / |entry−stop|`.
- `leverage.py` — детерминированная таблица (setup_type × intent) под cap `MAX_LEVERAGE`.
- `watcher.py` — реконсиляция OPEN: выходы по свечам (stop приоритетнее target внутри бара), expiry, delisting, extreme funding; `pnl.py` (price − fees − funding); обновление equity.
- При открытии/закрытии — `app/notifications/positions.py` шлёт карточку в Telegram (fire-and-forget, не ломает торговлю).

---

## 7. Данные и БД

**Торговая БД (MariaDB, `db/`)** — источник истины, миграции Alembic:
- `account`, `signal`, `virtual_position`, `event`, `system_state`.
- Доступ через `db/repositories/*` (паттерн Repository).
- `strategy_version` на `signal` сегментирует эпохи стратегии (сейчас **1.4.0**).

**Исследовательская БД (MariaDB, `db/research/`)** — регенерируемое аналитическое хранилище (`create_all`, без Alembic):
- `signal_record` — строка на каждого оценённого кандидата: весь контекст решения.
- `agent_output` — выход каждого из 4 аналитиков (4 строки на сигнал).
- `trade_outcome` — итог закрытой сделки (R-multiple, exit_reason, holding).
- Заполняется `db/research/writer.py`; читается `scripts/research/*`.

---

## 8. Внешние клиенты (`app/clients/`)

| Клиент | Данные |
|---|---|
| `ccxt` | Свечи, тикеры, funding history (унифицированный интерфейс биржи) |
| `binance` | OI, long/short ratio, CVD (Binance-специфика) |
| `coinglass` | Кросс-биржевые OI/ликвидации/funding, top-trader ratio, fear&greed |
| `coingecko` | Макро (BTC dominance, цена, изменения) |
| `lunarcrush` | Соц-сентимент, новости, посты, attention, AI-narrative |
| `llm` | litellm + instructor (structured output) |
| `telegram` | aiogram, исходящие уведомления |

`_shared/` — единое логирование ошибок (`errors.py`) и `rate_limiter.py`.

---

## 9. Инфраструктура

- **LLM-gateway** (`app/llm_gateway/`): `service.LLMService.structured()` поверх `app/clients/llm`; `budget.py` — дневной бюджет-гейт (`LLM_DAILY_BUDGET_USD`), cost-tracking.
- **Settings** (`core/settings.py`): pydantic-settings из `.env`, frozen; computed-поля (DATABASE_URL, LLM-модели, TELEGRAM_ENABLED).
- **Constants** (`core/constants/`): decisions, entities, http, llm, markets, time.
- **Prompts** (`core/prompts/`): yaml + `loader.py` + `models.py`.
- **Logging** (`app/logger.py`): структурный JSON, поля контекста (symbol, confluence, decision_reason).
- **Startup** (`app/startup.py`): `preflight()` — проверка обязательных ключей под провайдера; лог статуса Telegram.

---

## 10. Деплой и прод

- Docker: `Dockerfile` (uv sync `--frozen --no-default-groups`), `docker compose` сервисы: `worker`, `db` (MariaDB), `backup`, `migrate`.
- Секреты — в `.env` на сервере (не в образе).
- Миграции торговой БД — отдельно (`alembic upgrade head`); worker не мигрирует сам. Research-БД — `create_all`, аддитивные колонки через ручной `ALTER`.
- Прод-сервер: `root@62.197.49.156` (paper-аккаунт, баланс ~$2k).

---

## 11. Качество и тесты

- `tests/unit/` — изолированная логика (no network/db, кроме `tmp_path`), зеркалит структуру `app/`.
- `tests/integration/` — против реальных зависимостей (помечены `@pytest.mark.integration`).
- mypy (strict-ish, null-safety), ruff (style + аннотации), coverage ratchet.
- Детерминированный риск-слой и форматтеры покрыты регресс-тестами; research-схема компилируется на MariaDB-диалекте без живой БД.

---

## 12. Карта ключевых файлов

```
app/scheduler.py            — 4h-цикл, watcher→pipeline, мягкая остановка
app/pipeline/runner.py      — оркестрация 5 стадий
app/pipeline/analysis.py    — анализ одного кандидата (аналитики→дебаты→setup-цепочка)
app/pipeline/persistence.py — Signal + Event + PortfolioManager, ранжирование слотов
app/aggregator.py           — взвешенное голосование 4 аналитиков
app/analysts/debate.py      — bull/bear/trader, apply_trader_verdict
app/levelcomputer.py        — SetupIntent → реальные цены (market entry, caps)
app/portfolio/manager.py    — pre-trade gates, сайзинг, открытие позиции
app/portfolio/watcher.py    — реконсиляция OPEN, выходы, PnL, equity
app/notifications/positions.py — Telegram-карточки open/close
core/settings.py            — конфиг (.env), пороги, веса
db/models/                  — торговая БД (источник истины)
db/research/                — аналитическое хранилище (контекст решений)
```

---

## 13. Технический долг и бэклог

**Уже реализовано:** outcome-tracking + feature attribution (`db/research/` + `scripts/research/`),
bull/bear/trader дебаты (`app/analysts/debate.py`), Devil's Advocate, confidence-shrinkage,
market-вход + ATR-стоп + потолок цели + сайзинг по `analyst_confluence` (v1.4.0).

**Открытые проблемы (по приоритету, из живого расследования на проде):**

| # | Проблема | Суть | Статус |
|---|---|---|---|
| 1 | **0 лонгов** | macro(BTC)+derivatives структурно медвежьи, скармливаются обоим исследователям в дебатах → bear всегда сильнее → трейдер не даёт long. Скринер лонги находит (93/353), но они умирают в дебатах | смена логики дебатов, ждёт отдельного захода |
| 2 | Trader-conviction якорь | gpt-4o якорит conviction на 0.70 → `confluence_score` вырожден. Обойдено: сайзинг/ранжирование переведены на `analyst_confluence` (v1.4.0) | обойдено, корень не устранён |
| 3 | Геометрия стоп/цель | было: тесный 5%-стоп в шуме + фантазийные цели 30–40%. Стоп→8%, цель→потолок 20% (v1.4.0) | сделано, мерим эффект |
| 4 | Мусор-символы | в юниверс проходят gold-токены (XAUT), мемы (币安人生). Нет фильтра по тренду/типу/возрасту, порог объёма низкий ($5M) | режет частоту — ждём данных (record-first) |
| C | Funding-аппроксимация | константная последняя ставка × циклы на entry-ноционал | minor |
| D | Нет проскальзывания/гэпов | филл ровно по stop_price | minor |
| E | Leverage косметический | не влияет на PnL, ликвидация не моделируется | low |

**Бэклог улучшений точности (research-обоснованный):** post-hoc калибровка confluence
(изотоническая регрессия на накопленных outcome'ах), order-flow microstructure features,
multi-timeframe alignment (1h+1w), setup-type-aware риск, cross-position correlation,
память между тиками.

**Дисциплина:** record-first — фичу записываем и валидируем на данных, гейтим только
после подтверждения. Не добавлять фильтры/пороги по гипотезе на малой выборке.
