# Архитектура

## Поток данных (один тик)

```
run_tick (app/scheduler.py)
│
├─ PositionWatcher.run         закрыть stop/target/expiry/funding/delisting по OPEN-позициям,
│   (app/portfolio/watcher.py)  обновить equity. Идёт ПЕРВЫМ — PM ниже видит свежие слоты/equity.
│
└─ run_pipeline (app/pipeline/runner.py)
   │
   ├─ 1. run_screener            универс ликвидных перпов → по каждому символу технические +
   │     (app/screener/)          деривативные сигналы → score/direction. Возвращает топ-N кандидатов.
   │
   ├─ 2. DataEnricher.enrich     соц-данные LunarCrush (per-symbol) + макро CoinGecko +
   │     (app/enricher/)          Fear&Greed CoinGlass. → EnrichmentResult.
   │
   ├─ 3. run_analysis            LLM-аналитики + синтез (см. ниже) → CandidateSignal на каждого.
   │     (app/pipeline/analysis.py)
   │
   ├─ 4. persist_signals         Signal + Event(snapshot). Для signal_ready → PortfolioManager
   │     (app/pipeline/persistence.py)  проходит риск-гейты и открывает VirtualPosition.
   │
   └─ 5. record_signals          зеркало в research-БД (аналитика), сбой не ломает торговлю.
         (db/research/writer.py)
```

## Стадия анализа (`run_analysis`)

`analyze_macro` вызывается **один раз** за прогон (макро общее), дальше по каждому кандидату:

- `analyze_derivatives` — деривативные сигналы (OI, funding, L/S, CVD, basis…).
- `analyze_sentiment` — соц-сентимент LunarCrush + Fear&Greed.
- `analyze_technical` — LangGraph-граф (`app/agents/technical/`): сначала Python считает уровни
  (`compute_facts` → `TechnicalFacts`), затем LLM интерпретирует.
- `aggregate_signals` (`app/aggregator.py`) — взвешенный синтез четырёх bias'ов → `SignalSynthesis`
  (overall_bias, confluence_score, конфликты, риски).

Если `confluence_score >= CONFLUENCE_GATE` и bias не Neutral → **setup-chain**:
- LLM выдаёт **SetupIntent** (намерение: тип входа, якоря стопа/тейка в ATR) — **без чисел**.
- `LevelComputer.resolve_setup` (`app/levelcomputer.py`) детерминированно превращает intent в
  **CryptoSetup** (реальные entry/stop/target, R:R, valid_hours). Числа считает Python, не LLM.

> Принцип: **LLM не генерирует числа**. LLM → намерение, Python → цены.

## Планировщик (`app/scheduler.py`)

- Тик привязан к закрытию 4h-бара (00/04/08/12/16/20 UTC) + лаг `_TICK_LAG_SECONDS` (60с) на готовность данных.
- **Первый тик идёт сразу при старте** (recovery открытых позиций + полный пайплайн), дальше — по 4h-границам.
- Сбой одного тика логируется и не роняет цикл. `SIGTERM/SIGINT` — мягкая остановка.
- Запуск: CLI-команда `run` (см. [operations.md](operations.md)); в Docker — сервис `worker`.

## Портфель и риск

- **Сайзинг** (`app/portfolio/sizing.py`): фиксированный риск на сделку, растущий с уверенностью
  (`RISK_PER_TRADE_MIN_PCT`..`MAX_PCT`). `qty = NAV × risk_pct / |entry − stop|`. Маржа/нотионал
  с баланса **не списывается** (баланс двигает только реализованный PnL при закрытии); долларовый
  размер позиции пишется в `VirtualPosition.notional` и в Event(POSITION_OPENED).
- **Риск-гейты** (`app/portfolio/manager.py`): drawdown-брейкер → лимит слотов → лимит по направлению →
  funding kill-switch → dedup по символу.
- **PnL** (`app/portfolio/pnl.py`): `realized = ценовой PnL − комиссии − funding`. Всё в `Decimal`.

## Деньги и время (инварианты)

- **Деньги — только `Decimal`** через `DecimalText` (`db/types.py`); в MariaDB это `NUMERIC(28,10)`. Float для денег запрещён в торговом пути.
- **Время — UTC-aware** через `UTCDateTime`: naive datetime отклоняется на bind.

## Две БД

- **Торговая** (`tradingagents`): account, signal, virtual_position, event, system_state. Схема — через Alembic.
- **Research** (`research`): signal_record, agent_output, trade_outcome — аналитика. Создаётся `create_all`
  в рантайме (вне Alembic). Деньги там — `Float` намеренно (это не system-of-record).
