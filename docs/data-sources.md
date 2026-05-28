# Источники данных (внешние API)

Каждый клиент — пакет `app/clients/<name>/` (async context manager). Ответы парсятся в Pydantic-модели
(`models.py`), ошибки логируются единообразно через `app/clients/_shared/errors.py`.

| Клиент | Что даёт | Ключ |
|---|---|---|
| `ccxt` | OHLCV (4h/1d), funding rate history. | не нужен |
| `binance` | Open Interest, long/short ratio, CVD (по фьючерсным свечам). | не нужен (публичные FAPI) |
| `coinglass` | Агрегированный OI, CVD, L/S топ-трейдеров, funding (OI-weighted), basis, ликвидации, Fear&Greed, altcoin season, unlocks. | `COINGLASS_API_KEY` |
| `coingecko` | Макро: BTC-доминация, изменения за 24h/7d. | опционально |
| `lunarcrush` | Соц-сигналы: sentiment, AI-narrative, новости, посты, time-series. | `LUNARCRUSH_API_KEY` |
| `llm` | Обёртка litellm + instructor для structured-output. | ключ провайдера |

## CoinGlass: тарифы и плановые эндпоинты

Активный тариф задаётся флагами `COINGLASS_*_PLAN`. Лимит req/min подбирается автоматически
(`CoinGlassPlanRate`). Плановые эндпоинты при выключенном флаге возвращают `[]` (не ошибка):
CVD, net-position, large orderbook (Standard+), liquidation heatmap/max-pain (Professional+),
altcoin season / futures-spot ratio / token unlocks (Startup+).

Клиент имеет собственный rate-limiter + семафор (≤2 одновременных запроса) + «ворота»: при HTTP 429
все запросы паузятся на `_RATE_LIMIT_PAUSE_S` и повторяются.

## Известные особенности и обработка ошибок

### CoinGlass basis: `code:500 "Server Error"` по части монет

Эндпоинт `/api/futures/basis/history` для **новых/неликвидных** монет (свежие листинги) возвращает
HTTP **200** с телом `{"code":"500","msg":"Server Error","data":null}` — у CoinGlass просто нет
посчитанного basis-ряда по этой монете. Для ликвидных (BTC, TON, …) тот же запрос отдаёт `code:0` с данными.

- Это **не наша ошибка** и **не HTTP-500**: запрос корректен, отличается только символ.
- Клиент превращает `code != 0` в `CoinGlassAPIError` (`app/clients/coinglass/exceptions.py`).
- Скринер ловит это per-symbol: `basis=None`, символ всё равно оценивается по остальным сигналам.
- Логируется на уровне **DEBUG** (`evaluate_symbol: CoinGlass basis no data for …`), чтобы не шуметь.

Что осталось **громким** (WARNING/ERROR), чтобы не потерять важное: невалидный ключ
(`CoinGlassAuthError`, валит прогон), исчерпание rate-limit, сеть/timeout, смена контракта
(`expected list/dict in 'data'`), любое неожиданное исключение.

### CoinGlass Fear & Greed: ответ — dict, а не list (известный баг)

`/api/index/fear-greed-history` возвращает `data` **словарём**, а `fetch_fear_greed_history` дёргает его
через `_get` (ожидает список и берёт `data[0]`) → `RuntimeError: expected list in 'data', got dict`.
Сейчас это ловится в enricher'е → `fear_greed=None` (не падает). **Фикс не внесён**: нужно читать через
`_get_obj` и разобрать dict. Пока Fear&Greed в сентимент-аналитик приходит как `None`.

### Деградация в скринере

Все CoinGlass-вызовы в `evaluate_symbol` идут через `asyncio.gather(return_exceptions=True)`:
сбой одного под-сигнала по одному символу не валит ни символ, ни весь прогон (кроме auth — он re-raise).
