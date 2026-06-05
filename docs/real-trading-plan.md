# Идея: реальная торговля на Bybit + переключатель demo↔live

> Статус: **идея, не начато.** Зафиксировано на будущее. Логику paper не ломаем ни на
> одной фазе — реальная торговля строится рядом и включается флагом.

## Целевая архитектура

```
account.mode = PAPER | LIVE   →  выбирает Broker
Broker (Protocol, adapters/broker/)
   ├─ PaperBroker   — симуляция (текущее поведение)
   └─ BybitBroker   — реальные ордера (ccxt), биржа = источник правды
ExecutionService(entry) и position-manager(exit) зовут Broker по режиму аккаунта.
Стратегия / скрининг / риск-гейты — БЕЗ изменений.
```

Ключевой принцип: стратегия mode-agnostic; различается только **execution-слой**.
Ложится на слоистую структуру: broker = adapter (L1), сервисы зовут его через Protocol.

---

## Фаза 0 — Схема и проводка режима (безопасно, поведение не меняется)

- `account`: `mode: ENUM(PAPER,LIVE) default PAPER`, `exchange: str default binance`.
- `virtual_position`: `mode`, `exchange_order_id` (null), `stop_order_id` (null),
  `fill_price` (null — реальный филл).
- `trade_outcome`: `mode`.
- Миграции. Всё дефолт PAPER → **ноль изменений в работе**.
- Закрывает вопрос «правильно ли пишем статистику для реала» — добавляем недостающие колонки.

## Фаза 1 — Broker-абстракция + PaperBroker (рефактор, поведение то же)

- `adapters/broker/base.py` — Protocol:
  `open_position · place_stop · move_stop · close_position · fetch_positions · fetch_fills · set_leverage`.
- `domain/models/`: value-объекты `Fill`, `ExchangePosition`, `OrderRef`.
- `adapters/broker/paper.py` — `PaperBroker`: оборачивает текущую симуляцию
  (open = филл по resolved-цене, close = реконструкция, стопы — no-op).
- `ExecutionService` и `watcher` ходят через `Broker` (фабрика `make_broker(account)`
  по `account.mode`). Для PAPER → PaperBroker → **поведение идентично**.
- Фундамент готов, прод тот же.

## Фаза 2 — BybitBroker на testnet (реальные ордера, изолированно)

- `adapters/broker/bybit.py` — через **ccxt** (мы уже им торгуем данные):
  `create_order` (market/limit), `set_leverage`, reduce-only **stop-ордер**,
  `cancel_order`, `fetch_positions`, `fetch_my_trades` (филлы).
- Ключи из **env/секретов** (отдельные testnet-ключи), не в БД.
- **Идемпотентность**: `clientOrderId` из signal_id + намерения — не задвоить ордер на ретрае.
- LIVE-тест-аккаунт на **Bybit testnet**.

## Фаза 3 — Live-исполнение: вход + реальные стопы

- ExecutionService(LIVE): ставит реальный entry-ордер → читает **фактический филл**
  → пишет `fill_price` + `exchange_order_id`.
- position-manager(LIVE): управляемый стоп = **реальный ордер на бирже**.
  Безубыток/трейлинг = отменить старый стоп-ордер + поставить новый reduce-only,
  сохранить `stop_order_id`.

## Фаза 4 — Reconciliation (биржа = правда для LIVE) ⭐

- В цикле LIVE position-manager: тянем реальные позиции + последние филлы, **сверяем БД**:
  - биржа показывает «закрыто» (стоп/тейк сработал, **ликвидация**, ручное)
    → закрываем в БД по реальной цене;
  - частичный филл → корректируем размер;
  - осиротевшие ордера → чистим.
- **Это и есть защита от рассинхрона.**

## Фаза 5 — API-эндпоинт + кнопка на фронте

- `POST /api/trading/mode {mode}` → ставит `account.mode`, с **аутентификацией +
  явным подтверждением** (типизированная фраза/токен — нельзя случайным кликом уйти в реал).
  Сейчас API только GET — это первый control-эндпоинт.
- В `GET /account` отдаём текущий режим — фронт показывает.
- Фронт: переключатель (красный при LIVE) + модалка подтверждения
  «Это реальные деньги на Bybit». Существующий `halted` остаётся аварийным стопом.

## Фаза 6 — Безопасный выход в реал

- BybitBroker: testnet → mainnet-ключи.
- **Жёсткие лимиты для LIVE**: малый max-notional, дневной лимит убытка → авто-halt.
- **Paper + live параллельно**: paper-аккаунт всегда (бейзлайн), live — малым размером.
  По колонке `mode` сравниваем paper vs live attribution.
- Постепенно поднимаем размер по мере доверия.

---

## Сквозная безопасность (на всех фазах)

- Ключи — env/секреты, **никогда** в БД/логах.
- Идемпотентные ордера (`clientOrderId`).
- Жёсткие caps для LIVE + мгновенный kill-switch (всё в paper / закрыть всё).
- Все денежные логи/алерты помечают режим (PAPER vs 🔴 LIVE).
- Reconciliation — страховка от рассинхрона.

## Оценка

Многонедельный проект с реальными деньгами. Критичные фазы — **2–4** (брокер +
реальные стопы + reconciliation). Фазы **0–1** безопасны (готовят почву, paper не трогают)
— с них и начинать. Тестнет проходим досконально перед mainnet.
