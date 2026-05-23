# scripts/research/ — калибровка сигналов скринера

Три CLI-скрипта для загрузки исторических данных, оценки качества сигналов
и автоматического запуска калибровки по расписанию.

---

## Что здесь и зачем

| Скрипт | Назначение |
| --- | --- |
| `collect_data.py` | Качает исторические 4h данные по топ-N перп-парам, сохраняет в `data/` |
| `analyze.py` | Считает IC, ICIR, decay-кривые; подбирает пороги; пишет `report.txt` |
| `calibrate.py` | Оркестратор: проверяет свежесть данных и запускает collect + analyze |

---

## Методология: что именно мы меряем

### Cross-sectional Spearman IC

**IC (Information Coefficient)** — ранговая корреляция Спирмена между сигналом и
форвардной доходностью.

Мы считаем **cross-sectional IC**: в каждый момент t берём все символы в панели,
ранжируем их по значению сигнала, ранжируем по форвардной доходности,
вычисляем корреляцию рангов. Один IC на период → усредняем по времени.

```text
t=1:  [BTC: sig=1, fwd=+2%]  [ETH: sig=0, -]  [SOL: sig=-1, fwd=-1%]  → IC₁
t=2:  [BTC: sig=0, -]        [ETH: sig=1, fwd=+3%]  [SOL: sig=1, fwd=+1%]  → IC₂
...
mean(IC₁, IC₂, ...) = mean cross-sectional IC
```

Это прямой ответ на вопрос "правильно ли сигнал ранжирует монеты в каждый момент?".
Именно это нужно для скринера.

> **Почему не per-symbol time-series IC?**
> Per-symbol считает corr(сигнал\_btc\_во\_времени, доходность\_btc\_во\_времени) —
> это отвечает на вопрос "хорошо ли работает сигнал для BTC", но не говорит,
> выбирает ли он BTC лучше ETH. Cross-sectional IC отвечает на правильный вопрос.

### ICIR (IC Information Ratio)

```text
ICIR = mean_IC / std_IC
t_stat = ICIR × √(n_periods)
```

Показывает **стабильность** сигнала. Сигнал с IC=0.04 и ICIR=0.8 надёжнее,
чем IC=0.07 и ICIR=0.3. Пороги: ICIR > 0.5 — приемлемо, > 1.0 — сильный сигнал.

### IC Decay (halflife предсказательной силы)

IC вычисляется при горизонтах 4h, 8h, 16h, 32h, 48h, 96h.

```text
Horizon:  4h    8h    16h   32h   48h   96h
sig_rsi:  0.06  0.04  0.02  0.01  0.01  0.00  → halflife ~16h
sig_ema:  0.04  0.04  0.03  0.03  0.02  0.01  → halflife >96h
```

Halflife определяет **правильную частоту** обновления скринера:
сигнал с halflife 16h бессмысленно смотреть раз в сутки.

### IS / OOS split (защита от overfit)

Данные делятся по времени: первые 70% — in-sample (IS), последние 30% — out-of-sample (OOS).

- Пороги подбираются **только на IS** (threshold sweep)
- Итоговая таблица показывает **оба** IC\_IS и IC\_OOS
- Если IC\_OOS близок к IC\_IS — сигнал реален. Если IC\_OOS ≈ 0 — overfit

| IC | Что значит |
| --- | --- |
| 0.00 | Нет предсказательной силы |
| 0.03 | Слабый, но потенциально полезный |
| 0.05 | Хороший (уровень реальных квант-стратегий) |
| 0.10+ | Очень сильный (редкость в crypto) |

---

## Предварительные требования

```bash
uv sync --group research
```

Переменные окружения из `.env`:

- `BINANCE_API_KEY` / `BINANCE_API_SECRET` — для OI, L/S ratio и CVD через Binance FAPI

---

## Шаг 1: сбор данных

```bash
python scripts/research/collect_data.py [--symbols N] [--days N] [--min-volume USD] [--refresh]
```

| Параметр | Умолчание | Описание |
| --- | --- | --- |
| `--symbols` | 200 | Лимит монет после фильтрации по объёму |
| `--days` | 90 | Глубина истории (OI/L/S ограничены ~83 днями Binance) |
| `--min-volume` | 5 000 000 | Минимальный суточный объём в USD (фильтрует неликвидные пары) |
| `--refresh` | — | Перекачать даже если файл уже есть |

Binance Futures имеет 300+ USDT-перп пар, но большинство — низколиквидные альткоины с
объёмом < $1M/сутки. Фильтр по умолчанию ($5M) оставляет ~80–120 реально торгуемых пар
и исключает шум из IC-расчётов.

Каждый символ → `scripts/scripts/research/data/<SYMBOL>.parquet`:

```text
open, high, low, close, volume   (OHLCV 4h)
funding_rate                     (ffill с 8h интервала ccxt)
open_interest                    (Binance FAPI 4h)
long_short_ratio                 (Binance global L/S 4h)
vol_delta                        (per-period taker delta = buy_vol*2 - total_vol)
```

---

## Шаг 2: анализ

```bash
python scripts/research/analyze.py [--forward-hours N] [--data DIR]
```

| Параметр | Умолчание | Описание |
| --- | --- | --- |
| `--forward-hours` | 12 | Горизонт форвардной доходности (кратно 4) |
| `--data` | scripts/scripts/research/data/ | Папка с parquet-файлами |

Что делает:

1. Строит cross-sectional панели (timestamp × symbol) для всех сигналов
2. IS/OOS split по времени: 70% / 30%
3. Считает Spearman IC, ICIR, t-stat → `IC table` для каждого сигнала
4. Строит IC decay кривые (горизонты 4h..96h)
5. Sweep порогов **на IS** для 5 ключевых параметров → `recommended_thresholds.json`
6. Печатает отчёт и сохраняет `report.txt`

```bash
python scripts/research/analyze.py --forward-hours 12
python scripts/research/analyze.py --forward-hours 24
```

---

## Шаг 3: автозапуск (calibrate.py)

```bash
python scripts/research/calibrate.py               # запустит если данные > 90 дней
python scripts/research/calibrate.py --force       # принудительный перезапуск
python scripts/research/calibrate.py --check-only  # статус без запуска
python scripts/research/calibrate.py --max-age-days 60
```

Добавить в cron (каждое 3-е число в 3:00):

```bash
0 3 3 * * cd /path/to/TradingAgents && python scripts/research/calibrate.py >> scripts/research/calibrate.log 2>&1
```

`main.py` автоматически предупреждает в логах если данные устарели:

```text
WARNING — Calibration data is 95 days old. Run: python scripts/research/calibrate.py
```

---

## Применение результатов

1. Открой `scripts/research/report.txt`
2. **IC table**: оставляй только сигналы с |t\_stat| > 1.5 И IC\_OOS близким к IC\_IS
3. **Decay**: halflife < 8h → смотри скринер чаще; halflife > 48h → ежедневно достаточно
4. **Sweep**: пороги с ICIR > 0.5 и hit\_rate > 1% переноси в `settings.py`
5. **ICIR < 0.5** — сигнал нестабилен, рассмотри исключение из score

---

## Известные ограничения

| Ограничение | Влияние |
| --- | --- |
| 90 дней = 1 рыночный режим | IC может быть правильным в тренде и ложным в коррекции |
| Binance only (OI, L/S, CVD) | Нет multi-exchange агрегации |
| Survivorship bias | Топ-50 сейчас ≠ топ-50 90 дней назад, завышает IC |
| Нет HAC-коррекции | t-stat немного завышен из-за автокорреляции; смотреть `t > 2.0` |
| Нет дивергенций | RSI divergence, CVD price divergence не векторизуются — не включены |
| OOS = 30 дней | Мало для полноценной оценки; достаточно для sanity check |
