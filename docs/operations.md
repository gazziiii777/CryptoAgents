# Эксплуатация

## CLI-команды

Точка входа — `python -m cli` (в Docker: `docker compose run --rm app <cmd>`; локально: `uv run python -m cli <cmd>`).

| Команда | Что делает |
|---|---|
| `run` | Планировщик: первый тик сразу, далее каждые 4h (watcher → pipeline). Делает миграции + preflight на старте. Это и есть сервис `worker`. |
| `run --once [-n N]` | Один полный тик и выход. `-n` — ограничить юнивёрс топ-N пар (дёшево/быстро). |
| `pipeline [-n N]` | Только пайплайн (screener→enricher→анализ→persist), без watcher-реконсиляции. |
| `watch` | Один тик PositionWatcher: реконсиляция OPEN-позиций и применение выходов. |
| `keys-check` | Показать, какие API-ключи подхвачены (значения маскируются). exit 1 — нет required. |
| `account-create --name … --balance …` | Создать paper-аккаунт. |
| `halt-trading [--reason …]` / `resume-trading` | Пауза/возобновление новых входов. |
| `force-close --position-id N` | Принудительно закрыть позицию по последней 4h-цене. |
| `manual-signal --symbol … --side … --entry … --stop … --target …` | Ручной сигнал в обход скринера через риск-гейты PM. |

> `main.py` (`uv run python main.py`) — разовый прогон пайплайна **без** watcher, миграций и preflight.
> Для постоянной работы используйте `run` / сервис `worker`, не `main.py`.

## Миграции (Alembic, MariaDB)

Схему применяет сервис `migrate` (`alembic upgrade head`) или вручную.

**Новая миграция после изменения моделей:**
```bash
make migration MSG="add foo"          # = docker compose run --rm app alembic revision --autogenerate
docker compose up -d                  # migrate применит
```

**Пересоздать initial-миграцию с нуля** (например, после смены БД): удалить `migrations/versions/*.py`,
поднять чистую `db`, сгенерировать заново. С хоста:
```bash
DB_HOST=127.0.0.1 uv run alembic revision --autogenerate -m "initial schema"
DB_HOST=127.0.0.1 uv run alembic upgrade head
```

> ⚠️ Документированная команда `docker compose run --rm app alembic ...` напрямую не сработает:
> у сервиса `app` ENTRYPOINT = `python -m cli`, поэтому получится `python -m cli alembic …`.
> Нужно переопределять entrypoint: `docker compose run --rm --entrypoint alembic app revision ...`.

Research-БД миграций не имеет — таблицы создаются `create_all` в рантайме.

## Качество кода

```bash
make lint          # ruff check
make format.check  # ruff format --check
make typecheck     # mypy (app, core, db, cli, main.py)
make test          # pytest tests/unit (in-memory SQLite)
make check         # всё вместе (CI-гейт)
```

Юнит-тесты используют in-memory SQLite (`tests/unit/conftest.py`), а не MariaDB — поэтому быстрые и без сервиса.

## Диагностика частых проблем

| Симптом | Причина / решение |
|---|---|
| `invalid compose project: worker depends on undefined service migrate` | Не активен профиль `init`. Поставь `COMPOSE_PROFILES=init` в `.env` или префиксом команды. |
| Контейнер коннектится к SQLite (`unable to open database file`) | Устаревший образ со старой `settings.py`, либо в `.env` лежит старый `DATABASE_URL=sqlite…`. Пересобери образ (`--build`); `DATABASE_URL` теперь вычисляемый и значение из `.env` игнорируется. |
| `error: command 'gcc' failed` при сборке | Был драйвер `asyncmy` (нужна компиляция). Перешли на `aiomysql` (pure-python). Если вернулось — проверь, что в зависимостях `aiomysql`, а не `asyncmy`. |
| После старта worker `sleeping until next tick`, пайплайн не идёт | Так было раньше: первый тик откладывался до 4h-границы. Сейчас первый тик идёт сразу при старте. Если видишь старое поведение — пересобери worker (`docker compose up --build -d worker`). |
| `LiteLLM:WARNING ... could not pre-load sagemaker-runtime ... No module named 'botocore'` | Безобидный warning litellm (нет AWS/Bedrock). Игнорировать. |
| `CoinGlass basis ... Server Error` (DEBUG) | Норма: у CoinGlass нет basis-данных по неликвидной монете. Не ошибка. См. [data-sources.md](data-sources.md). |
| `Event loop is closed` в `aiomysql Connection.__del__` при остановке | Чинится: планировщик зовёт `dispose_engine()`/`dispose_research_engine()` в `finally`. Если всплыло — пересобери worker. |

## Бэкапы БД

Сервис `backup` (сайдкар в `docker-compose.yml`) периодически делает логический дамп обеих БД
(`mariadb-dump` → gzip) в `./backups` и ротирует старые. Запускается вместе с `docker compose up`.

- Интервал и retention — `DB_BACKUP_INTERVAL_S` (дефолт 86400 = раз в сутки), `DB_BACKUP_RETENTION_DAYS` (7).
- Восстановление: `gunzip -c backups/tradingagents_<ts>.sql.gz | docker compose exec -T db mariadb -u tradingagents -p<pass> tradingagents`.
- Логи: `docker compose logs -f backup`.

## Полезное

```bash
make db.shell      # MariaDB CLI внутри контейнера
make logs          # tail логов worker
make db.url        # креды для GUI (Sequel Ace): host 127.0.0.1:3306
```
