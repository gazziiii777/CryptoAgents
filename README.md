# TradingAgents

Многоагентный свинг-трейдинг крипто-перпетуалов, таймфрейм **4h**, **paper** (виртуальные
позиции). Каждые 4 часа: отбор монет → цепочка LLM-аналитиков → детерминированный
риск-менеджер → открытие/закрытие виртуальных сделок → уведомления в Telegram.

Принцип: **числа (деньги, риск, уровни) считает Python, LLM даёт только направления и
категории.** Контекст каждого решения пишется в research-БД для анализа.

## Как работает один тик

```
закрытие 4h-бара
   │
   ├─ WATCHER: закрыть OPEN по stop/target/expiry/funding/delisting → PnL, equity → TG «закрыто»
   │
   └─ PIPELINE:
        перпы биржи ─►[объём ≥$5M]─► SCREENER ─►[ADX≥20, score≥4, топ-15]─► ENRICHER (соц+макро)
          ─► 4 аналитика (macro·derivatives·sentiment·technical)
          ─► АГРЕГАТОР (взвеш. голосование) ─► ДЕБАТЫ bull/bear ─► TRADER: long/short/no_trade
          ─► SETUP (вход/стоп/цель) ─► RISK ─► DEVIL'S ADVOCATE
          ─► PORTFOLIO MANAGER (4 проверки + сайзинг) ─► открыть позицию ─► TG «открыто»
```

- **Screener** — технические (ADX/RSI/MACD/EMA/VWAP) + деривативные (funding/OI/L-S/CVD) сигналы → score.
- **Аналитики** — 4 LLM-отчёта; **агрегатор** взвешивает (technical 0.35, derivatives 0.25, macro/sentiment 0.20), порог bias ±0.15, `confluence = |голоса|×0.75`.
- **Дебаты** — bull/bear (gpt-4o-mini) → trader (gpt-4o) выносит вердикт; гейт `confluence ≥ 0.50`.
- **LevelComputer** — вход по market, стоп ATR в `[0.3%, 8%]`, цель ≤20%, R:R ≥1.5.
- **PortfolioManager** — drawdown-breaker / слоты (5) / направление (2) / funding kill-switch; риск `0.5–2%` NAV по уверенности, плечо из таблицы (cap ×10).
- **Выход** — stop/target (стоп приоритетнее внутри свечи) / expiry / delisting / extreme funding. PnL = цена − комиссии − фандинг.

## Запуск

```bash
cp .env.example .env          # ключи: LUNARCRUSH / COINGLASS / OPENAI (+ опц. TELEGRAM_*)
COMPOSE_PROFILES=init docker compose up --build -d
docker compose logs -f worker
```

Локально без Docker:
```bash
uv sync
uv run python -m cli run --once --limit 15    # smoke по топ-15
uv run python -m cli run                       # scheduler-цикл (4h)
```

CLI: `run` (`--once`), `watch`, `pipeline`, `manage`, `keys_check`.

## Конфигурация (`core/settings.py`, override через `.env`)

| Параметр | Знач. | Смысл |
|---|---|---|
| `UNIVERSE_MIN_VOLUME_USD` | $5M | порог ликвидности |
| `ADX_GATE_MIN` / `SCREENER_MIN_SCORE` / `SCREENER_TOP_N` | 20 / 4 / 15 | прохождение скринера |
| `CONFLUENCE_GATE` / `CONFIDENCE_SHRINKAGE` | 0.50 / 0.75 | гейт + коррекция overconfidence |
| `MAX_CONCURRENT_POSITIONS` / `MAX_SAME_DIRECTION` | 5 / 2 | портфельные лимиты |
| `RISK_PER_TRADE_MIN/MAX_PCT` / `MAX_LEVERAGE` | 0.5–2% / ×10 | сайзинг и плечо |
| `DRAWDOWN_HALT_PCT` / `FUNDING_KILL_SWITCH_PCT` | 10% / 0.25% | защитные выключатели |

## Данные

- **Торговая БД** (MariaDB, Alembic) — источник истины: `account`, `signal`, `virtual_position`, `event`.
- **Research-БД** (`create_all`) — контекст решений: `signal_record`, `agent_output`, `trade_outcome`.
- `strategy_version` сегментирует эпохи (сейчас **1.4.0**). Офлайн-аналитика — `scripts/research/`.

## Документация

- [ARCHITECTURE.md](ARCHITECTURE.md) — слои, пакеты, поток, тех-долг
- [docs/setup.md](docs/setup.md) · [docs/configuration.md](docs/configuration.md) · [docs/operations.md](docs/operations.md) · [docs/data-sources.md](docs/data-sources.md)
