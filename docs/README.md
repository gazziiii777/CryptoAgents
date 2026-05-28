# Документация TradingAgents

Актуальная (после переезда на MariaDB) документация проекта. Сгруппирована по задачам.

| Документ | О чём |
| --- | --- |
| [architecture.md](architecture.md) | Компоненты и поток данных: screener → enricher → аналитики → синтез → setup → портфель. Планировщик 4h. |
| [setup.md](setup.md) | Локальный запуск через Docker Compose (MariaDB), `.env`, миграции. |
| [configuration.md](configuration.md) | Справочник переменных окружения (из `core/settings.py`). |
| [data-sources.md](data-sources.md) | Внешние API (Binance, ccxt, CoinGlass, LunarCrush, CoinGecko), тарифы, известные особенности. |
| [operations.md](operations.md) | CLI-команды, работа с миграциями, диагностика частых проблем. |

## Что это за проект

Система генерации крипто-торговых сетапов (perpetual futures, таймфрейм 4h, **paper trading** —
виртуальные позиции, без реальных ордеров). Каждые 4 часа:

1. **Screener** отбирает ликвидные пары и считает технические/деривативные сигналы.
2. **Enricher** добавляет соц-данные (LunarCrush) и макро (CoinGecko / CoinGlass).
3. **LLM-аналитики** (macro, derivatives, sentiment, technical) дают bias; **агрегатор** считает confluence.
4. **LevelComputer** превращает намерение (SetupIntent от LLM) в конкретные цены (CryptoSetup).
5. **PortfolioManager** проходит риск-гейты и открывает `VirtualPosition`.
6. **PositionWatcher** на следующих тиках закрывает позиции по stop/target/expiry/funding.

## Бэклог улучшений

- [signal-accuracy-roadmap.md](signal-accuracy-roadmap.md) — gap-анализ vs
  best practices (TauricResearch, TrustTrade, microstructure research) и
  приоритезированный список добавлений: outcome tracking, Bull/Bear debate,
  confidence calibration, order-flow features, leverage. **Делать в этом порядке.**

## Легаси-доки (vision / roadmap)

Историко-проектные документы (перенесены из корня репозитория). Раздел persistence писался под
SQLite — внутри добавлены баннеры о переезде на MariaDB:

- [architecture-roadmap.md](architecture-roadmap.md) — полная роадмапа.
- [architecture-mvp.md](architecture-mvp.md) — что входит в MVP и принципы качества.
- [status.md](status.md) — статус/план.
- [subscriptions.md](subscriptions.md) — какие тарифы провайдеров нужны.

При расхождении источником правды считать код и актуальные доки выше.
