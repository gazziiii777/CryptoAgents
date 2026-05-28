# CryptoAgents

Генерация крипто-торговых сетапов (perpetual futures, таймфрейм 4h, **paper trading** —
виртуальные позиции, без реальных ордеров): screener → enricher → LLM-аналитики → риск-менеджер.

## 📖 Документация — в [`docs/`](docs/)

| | |
|---|---|
| [docs/setup.md](docs/setup.md) | Установка и запуск (Docker Compose + MariaDB), `.env`, миграции |
| [docs/architecture.md](docs/architecture.md) | Как всё устроено: поток данных, планировщик, портфель |
| [docs/configuration.md](docs/configuration.md) | Справочник переменных окружения |
| [docs/data-sources.md](docs/data-sources.md) | Внешние API и их особенности |
| [docs/operations.md](docs/operations.md) | CLI-команды, миграции, диагностика |
| [docs/README.md](docs/README.md) | Индекс + легаси vision/roadmap-доки |

## Быстрый старт

```bash
cp .env.example .env                          # впиши ключи: LUNARCRUSH / COINGLASS / OPENAI
COMPOSE_PROFILES=init docker compose up --build -d
docker compose logs -f worker
```

Подробнее — [docs/setup.md](docs/setup.md).
