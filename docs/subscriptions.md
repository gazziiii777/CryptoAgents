# Подписки на API-провайдеров

Что реально нужно для пайплайна и за что платить. Обновлено: 2026-05-24.

## Итог (TL;DR)

Для **текущего пайплайна (Iter 1: screener + enricher) платных апгрейдов не требуется.**
Минимально необходимое (что и так есть в `.env`):

| Провайдер | Тариф | Нужен? | Стоимость |
|---|---|---|---|
| **CoinGlass** | Hobbyist (минимальный — free-tier у них **нет**) | ✅ да, базовый | ~$29–35/мес |
| **LunarCrush** | базовый платный план | ✅ да, базовый | (текущий) |
| **CoinGecko** | free-tier (без ключа) | ⛔ подписка не нужна | $0 |
| **Binance / ccxt** | публичные market-data | ⛔ ключ/подписка не нужны | $0 |
| **Anthropic** | API (pay-as-you-go) | 🔜 нужен для Iter 2 (LLM) | по токенам |

`COINGECKO_API_KEY` сейчас MISSING — и это **ок**: macro отрабатывает на free-tier (подтверждено живым прогоном). Ключ опционален, только ради rate-limit.

## По провайдерам

### CoinGlass — нужен платный план (free-tier нет)
Тариф задаётся флагами в `.env`; по умолчанию все `False` → **Hobbyist** (28 req/min в лимитере).
Соответствие тариф → лимит → цена (из `app/clients/coinglass/client.py:CoinGlassPlanRate`):

| Тариф | req/min | ~цена/мес | Флаг |
|---|---|---|---|
| Hobbyist | 30 | $29–35 | (дефолт) |
| Startup | 80 | $79–95 | `COINGLASS_STARTUP_PLAN` |
| Standard | 300 | $299–379 | `COINGLASS_STANDARD_PLAN` |
| Professional | 1200 | $699–879 | `COINGLASS_PROFESSIONAL_PLAN` |

**Screener использует только не-gated эндпоинты** (liquidation aggregated history, top position ratio, funding-rate OI-weight, futures basis) → **Hobbyist достаточно**.

Платный апгрейд нужен только под gated-данные (код уже возвращает `[]` без флага):
- **Startup+**: aggregated CVD history, net-position history, altcoin season.
- **Standard+**: large orderbook.
- **Professional+**: liquidation **heatmap**, **max pain**. ← понадобятся для `liq_cluster` references в **Iter 3 (SetupIntent/LevelComputer)**.

### LunarCrush — базовый план хватает, Builder НЕ нужен
Лимит ~10 req/min (shared между api4 и lunarcrush.ai). Текущий план покрывает: `/coins/list`, `/topic/{t}/news|posts|time-series`, `lunarcrush.ai/topic/{t}` (lc_context).

**Builder-план (whatsup) не нужен:** структурный AI-narrative/themes (`/topic/{t}/whatsup`) отключён (`LUNARCRUSH_WHATSUP_ENABLED=false`) — тот же нарратив и темы приходят в `lc_context` (markdown), который доступен на текущем плане. Включать Builder только если захотим именно структурный whatsup вместо markdown (не обязательно).

### CoinGecko — free, подписка не нужна
`/global` + `/coins/markets` для macro работают **без ключа** (free-tier, подтверждено). `COINGECKO_API_KEY` опционален — только ради повышенного rate-limit/надёжности.

### Binance / ccxt — бесплатно
Публичные market-data (OHLCV, funding, OI, long/short) — ключ не требуется.

## Когда возвращаться к этому вопросу
- **Iter 3** (SetupIntent с `liq_cluster`) → возможно **CoinGlass Professional** (heatmap/max-pain). До этого — нет.
- Упёрлись в rate-limit CoinGecko → добавить `COINGECKO_API_KEY`.
- Нужен структурный whatsup → **LunarCrush Builder** (иначе нет).
