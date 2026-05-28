# Установка и запуск (локально)

## Стек

- Python 3.12 (Docker-образ), управление зависимостями — [uv](https://docs.astral.sh/uv/).
- БД — **MariaDB 11** (драйвер `aiomysql`, чисто-python, без компиляции).
- ORM/миграции — SQLAlchemy/SQLModel + Alembic.
- LLM — litellm + instructor; данные — ccxt, python-binance, httpx.

## 1. `.env`

Скопируй пример и впиши ключи:

```bash
cp .env.example .env
```

Обязательные ключи: `LUNARCRUSH_API_KEY`, `COINGLASS_API_KEY` и ключ выбранного LLM-провайдера
(`OPENAI_API_KEY` при `LLM_PROVIDER=openai`). Подключение к БД и `COMPOSE_PROFILES=init` уже в примере.
Полный справочник — [configuration.md](configuration.md).

> `DATABASE_URL`/`RESEARCH_DATABASE_URL` — **вычисляемые** поля (из `DB_HOST/DB_USER/...`), их в `.env`
> задавать не нужно. Значения по умолчанию совпадают с сервисом `db` в `docker-compose.yml`.

## 2. Запуск через Docker Compose (рекомендуется)

```bash
docker compose up --build -d        # поднимает db → migrate (alembic upgrade head) → worker
docker compose logs -f worker       # логи планировщика
```

> **Важно:** для локального запуска нужен профиль `init` (иначе сервис `migrate` отключён, а `worker`
> от него зависит → "invalid compose project"). Профиль берётся из `COMPOSE_PROFILES=init` в `.env`.
> Если не прописал в `.env` — запускай как `COMPOSE_PROFILES=init docker compose up --build -d`.

Сервисы (`docker-compose.yml`):

| Сервис | Назначение |
|---|---|
| `db` | MariaDB 11. Данные на хосте в `./mariadata`, порт `127.0.0.1:3306`. Создаёт базы `tradingagents` + `research`. |
| `migrate` | Разовый job: `alembic upgrade head`. Профиль `init`. Worker ждёт его завершения. |
| `worker` | Долгоживущий планировщик (`cli run`, 4h-тик). `restart: unless-stopped`. |
| `app` | Разовые команды: `docker compose run --rm app <cmd>`. |

## 3. Миграции

Образ собирается с текущими моделями; `migrate` применяет `alembic upgrade head`. Подробно — в [operations.md](operations.md).

## 4. Локальный запуск без Docker (опционально)

```bash
uv sync --frozen
```

Для команд, ходящих в БД (alembic, watch, pipeline c записью), с хоста БД доступна на `127.0.0.1`,
поэтому переопредели хост: `DB_HOST=127.0.0.1` (имя `db` резолвится только внутри docker-сети).

```bash
DB_HOST=127.0.0.1 uv run alembic upgrade head
DB_HOST=127.0.0.1 uv run python -m cli run --once -n 6
```

## Проверка ключей

```bash
docker compose run --rm app keys-check     # exit 1, если нет required-ключа
```
