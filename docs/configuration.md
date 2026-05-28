# Конфигурация (переменные окружения)

Все настройки — в `core/settings.py` (pydantic-settings, читает `.env`). Каждое поле имеет дефолт;
переопределять нужно только при необходимости. **Обязательны лишь API-ключи.**

`DATABASE_URL` и `RESEARCH_DATABASE_URL` — **вычисляемые** (computed) поля, собираются из `DB_*`;
их в `.env` не задают.

## Docker / Compose

| Переменная | Дефолт | Назначение |
|---|---|---|
| `COMPOSE_PROFILES` | — | Для локального `docker compose up` ставь `init` (включает сервис `migrate`). |
| `DB_ROOT_PASSWORD` | `tradingagents_root` | Root-пароль MariaDB-контейнера. |

## База данных

| Переменная | Дефолт | Примечание |
|---|---|---|
| `DB_HOST` | `db` | Внутри docker — `db`. С хоста — `127.0.0.1`. |
| `DB_PORT` | `3306` | |
| `DB_USER` | `tradingagents` | |
| `DB_PASSWORD` | `tradingagents` | |
| `DB_NAME` | `tradingagents` | Торговая БД. |
| `DB_RESEARCH_NAME` | `research` | Research/аналитическая БД. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_RECYCLE_S` | `5` / `10` / `3600` | Пул соединений. |

> Если меняешь `DB_USER`/`DB_NAME` в `.env`, в `docker-compose.yml` сервис `db` создаёт их хардкодом —
> приведи `MARIADB_USER`/`MARIADB_DATABASE` к тем же переменным, иначе коннект не сойдётся.

## API-ключи

| Переменная | Обязателен | Примечание |
|---|---|---|
| `LUNARCRUSH_API_KEY` | да | Соц-данные. |
| `COINGLASS_API_KEY` | да | Деривативы/макро. |
| `OPENAI_API_KEY` | да* | *при `LLM_PROVIDER=openai`. |
| `ANTHROPIC_API_KEY` | да* | *при `LLM_PROVIDER=anthropic`. |
| `COINGECKO_API_KEY` | нет | Опционально (повышенные demo-лимиты). |

Стартовый `preflight` (в команде `run`) падает, если нет required-ключа под выбранного провайдера.

## LLM

| Переменная | Дефолт | |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` \| `anthropic`. Модели выбираются автоматически по провайдеру. |
| `LLM_DAILY_BUDGET_USD` | `5.0` | Жёсткий дневной потолок расходов (budget gate). |
| `LLM_MAX_OUTPUT_TOKENS` | `4096` | |
| `LLM_MAX_RETRIES` | `2` | |
| `LLM_TEMPERATURE` | `0.2` | |
| `LLM_TIMEOUT_S` | `60` | Таймаут одного вызова LLM. |

## Тарифы CoinGlass

`COINGLASS_STARTUP_PLAN` / `COINGLASS_STANDARD_PLAN` / `COINGLASS_PROFESSIONAL_PLAN` (все `false`).
Открывают плановые эндпоинты (CVD, net-position, large orderbook, liquidation heatmap/max-pain и т.д.).
Без флага соответствующий клиент возвращает `[]` без ошибки. См. [data-sources.md](data-sources.md).

## Биржа / скринер / соц / риск

Остальные параметры (UNIVERSE_MIN_VOLUME_USD, SCREENER_*, ADX_GATE_MIN, RSI_*, FUNDING_*, LS_RATIO_*,
LUNARCRUSH_*, RISK_PER_TRADE_*, MAX_CONCURRENT_POSITIONS, DRAWDOWN_HALT_PCT, TAKER_FEE_RATE, …) —
с рабочими дефолтами в `core/settings.py`, закомментированы в `.env.example`. Меняй точечно.

Калибровка порогов скринера — офлайн-скриптами в `scripts/research/` (на live-пайплайн не влияют).
