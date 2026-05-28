# Roadmap: повышение точности сигналов

Backlog улучшений LLM-агентов и сигнальной системы, основанный на анализе
текущей архитектуры и обзоре best practices (multi-agent LLM frameworks 2024–2026,
calibration research, microstructure trading). Документ описывает **что есть**,
**что в литературе считается правильным**, **где гэп**, и **в каком порядке закрывать**.

Это **бэклог**, не roadmap-обязательство. По мере получения данных (закрытых сделок)
часть пунктов может оказаться неактуальной — переоценивать каждый спринт.

## Статус

- ✅ **Спринт 1** (реализовано, протестировано, НЕ задеплоено): P1 (feature snapshot +
  `setup_type` fix + `scripts/research/attribution.py`), P3a (CONFIDENCE_SHRINKAGE 0.75),
  P6 (funding extreme contrarian).
- ✅ **Спринт 2** (реализовано, протестировано, НЕ задеплоено): P8 (LLM `leverage_intent`
  → детерминированное плечо + margin, миграция `ffdfd1dea751`), P2 (Bull/Bear/Trader
  debate в `app/analysts/debate.py`), P4 (Devil's Advocate veto в
  `app/analysts/devils_advocate.py`).
- ✅ **Спринт 1–2 ЗАДЕПЛОЕНЫ** на прод (62.197.49.156), БД обнулена для чистой
  статистики, миграция `ffdfd1dea751` применена.
- ✅ **Спринт 4 "Smart-money / manipulation awareness" Tier 1** (реализовано,
  протестировано, НЕ задеплоено): `smart_money_divergence` (top vs retail, в screener →
  derivatives prompt), `pump_risk` (соц-памп без новостей, в enricher → sentiment prompt),
  Devil's Advocate manipulation-чеклист. Обе фичи пишутся в `SignalRecord` (record-first)
  + разбивки в `attribution.py`. **Defensive**: фичи мягко влияют через DA/аналитиков, не
  жёсткие гейты — пока не подтверждены данными.
- 🔲 **Спринт 3** (после 100+ закрытых сделок): P3b, P5, P7, P9, P10.
- 🔲 **Спринт 4 Tier 2/3**: orderbook walls/спуфинг (нужна order-flow инфра),
  on-chain whale flows (CryptoQuant/Glassnode, платно), собственный liquidation heatmap.

**Деплой Спринта 4** требует только DROP research-БД (2 новые колонки в `signal_record`:
`smart_money_divergence`, `pump_risk`). Trading-БД НЕ меняется (миграция не нужна).

## 1. Текущая архитектура (recap)

```
Screener (Python, 15 критериев) → Enricher (LC + CG + F&G) →
  4 LLM-аналитика (Macro 0.20 / Derivatives 0.25 / Sentiment 0.20 / Technical 0.35) →
    Weighted vote → confluence_score → gate ≥ 0.55 →
      SetupBuilder (LLM: intent) → LevelComputer (Python: цены) →
        RiskValidator → PortfolioManager (4 gates + confidence-sized risk)
```

**Что уже соответствует best practice:**

- LLM не пишет числа — только `SetupIntent` (symbolic anchors + ATR multiples). Цены считает Python в `LevelComputer`.
- Risk math детерминирован (`portfolio/sizing.py`).
- Multi-stage gates (confluence → risk → drawdown → slot).
- Confidence-scaled risk per trade (`RISK_PER_TRADE_MIN_PCT`..`MAX_PCT`).
- Per-candidate isolation: один сбой не роняет тик.
- Decimal для денег, UTC tz-aware для времени.

## 2. Что говорит research

### 2.1 Adversarial debate > weighted voting

Публичный фреймворк [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
(arxiv [2412.20138](https://arxiv.org/pdf/2412.20138)) — это **тот же концепт**, что у нас,
но реализует:

- **Bull Researcher** строит bullish case.
- **Bear Researcher** строит bearish case.
- Debate (2–3 round trips) — каждый возражает другому.
- **Trader-agent** синтезирует решение после дебатов.
- **Risk Management team** (Aggressive / Conservative / Neutral) — отдельный слой.

[TrustTrade (arxiv 2603.22567)](https://arxiv.org/pdf/2603.22567) — "Selective Consensus":
cross-agent agreement в семантическом И числовом пространстве + dynamic credibility scores.
Конфликтующие сигналы down-weighted.

У нас сейчас плоское взвешенное голосование. Исследования сообщают **+20–40% accuracy**
от добавления adversarial debate в out-of-sample.

### 2.2 LLM систематически overconfident

[Anthropic / OpenAI calibration papers](https://arxiv.org/html/2512.16030):

> All current frontier models are overconfident, reasoning enhancements degrade
> calibration, and calibration and accuracy are largely decoupled.

Значит `confidence: 85` от нашего LLM **не** означает 85% win rate. Реальная — 55–65%.

Решение — **post-hoc калибровка**:
- Isotonic regression / Platt scaling после 100+ закрытых сделок.
- Метрики: **Brier score**, **Expected Calibration Error (ECE)**.
- До накопления данных — **shrinkage**: `effective = raw × 0.7`.

См. [5 Methods for Calibrating LLM Confidence Scores](https://latitude.so/blog/5-methods-for-calibrating-llm-confidence-scores).

### 2.3 Fractional Kelly = 1/4 Kelly для крипто

[Altrady](https://www.altrady.com/blog/risk-management/kelly-criterion-crypto-position-sizing),
[LBank](https://www.lbank.com/explore/mastering-the-kelly-criterion-for-smarter-crypto-risk-management):

- Half Kelly (50%) даёт ~75% growth, halves drawdown.
- **Quarter Kelly (25%)** — рекомендуется для крипто из-за высокой волатильности.
- "Full Kelly = ruin" при ошибках в win rate estimate.

Наш текущий fixed-fractional (`RISK_PER_TRADE_MIN_PCT=0.5%..MAX=2%`) — нормальный
дефолт пока нет win rate данных. Kelly без callibrated probabilities = катастрофа.

### 2.4 Order-flow microstructure features = structural edge

[Atas](https://atas.net/blog/heatmap/), [Bookmap](https://bookmap.com/en/why-bookmap):

Канонические microstructure-фичи:
- **Order Book Imbalance (OBI)** — bids/asks ratio на top of book.
- **Microprice** — взвешенная по qty fair value (лучше mid).
- **Volume Delta + CVD** (у нас есть).
- **Trade intensity** — частота сделок.
- **Liquidation heatmap proximity** — расстояние до ближайшего liq-кластера.

[Kalena.ai liquidation guide](https://blog.kalena.ai/liquidation-heatmap-where-leveraged-positions-go-to-die-and-how-smart-traders-get-there-first):

> The biggest edge isn't predictive — it's structural. You're not guessing
> direction. You're identifying where forced selling or buying MUST occur if
> price reaches a level.

## 3. Gap analysis

| Best practice | Наш статус | Severity |
|---|---|---|
| Bull/Bear adversarial debate | Flat weighted vote, без debate | **MAJOR** |
| Calibrated confidence | Raw LLM confidence, без коррекции | **MAJOR** |
| Outcome tracking → learning loop | `research.trade_outcome` есть, но без feature-attribution | **MAJOR** |
| Devil's Advocate agent | Запланирован, не реализован | MEDIUM |
| Order-flow features (OBI / microprice / liq-proximity) | Есть только CVD | MEDIUM |
| Multi-timeframe (1h refinement, 1w HTF) | 4h + 1d только | MEDIUM |
| Setup-type-aware risk / leverage | Single risk_pct по confluence | MINOR |
| Cross-position correlation awareness | Нет (только same-symbol dedup) | MINOR |
| Memory / cross-tick context | Stateless tick | MINOR |
| Funding extreme as contrarian signal | Linear funding_bias | MINOR |

## 4. Top-10 backlog (ranked by ROI / effort)

### P1 — Outcome tracking + feature attribution (foundation)

**Проблема.** Мы открываем позиции, но не пишем **почему** в форме доступной для
обратной связи. Когда позиция закрывается, нет ниточки "какие фичи реально
предсказали выигрыш / проигрыш".

**Что делать:**
- Расширить `research.trade_outcome` (или новая таблица `trade_features_snapshot`)
  полями на момент открытия:
  - 15 screener-флагов (`volume_spike`, `bb_squeeze`, `ema_cross`, `rsi_divergence`,
    `macd`, `vwap_bias`, `daily_trend`, `near_swing`, `oi_change_4h_pct`,
    `oi_trend`, `funding_bias`, `long_short_ratio`, `cvd_trend`,
    `cvd_price_divergence`, `liq_spike`).
  - 4 analyst bias (`macro_bias`, `derivatives_bias`, `sentiment_bias`,
    `technical_bias`).
  - Setup мета (`setup_type`, `confluence_score`, `llm_confidence`).
  - Контекст (`macro_regime`, `funding_at_open`, `atr_at_open`, `volatility_pct`).
- Когда watcher закрывает позицию — пишет `realized_pnl`, `bars_held`,
  `exit_reason`, `r_multiple` (= `realized_pnl / risk_at_open`).
- SQL-аналитика (отдельный CLI `python -m scripts.research.attribution`):
  - Per `setup_type` win rate, avg R-multiple.
  - Per `(setup_type, regime)` matrix.
  - Per analyst bias contribution to win rate.
  - LLM confidence vs realized outcome (для P3 калибровки).

**Стоимость:** ~4 часа кода + alembic-миграция (расширение таблицы).
**Зачем сейчас:** Без этого P3, P4, P8 — догадки. **Это фундамент.**

### P2 — Bull/Bear Researcher debate

**Что делать.** Между текущими 4 analysts и aggregator вставить debate-этап.

В `app/agents/debate/`:
- `BullResearcher` (1 LLM-call): "build strongest bullish case given the four reports"
- `BearResearcher` (1 LLM-call): "build strongest bearish case given same data"
- `Trader` (1 LLM-call, deep model): "given both cases, verdict — long / short / no-trade + reasoning"

Aggregator не убираем — оставляем как fallback / weight prior. Trader-agent
**уточняет** confluence_score, не **заменяет**.

Если bull/bear оба слабые → confluence снижается. Если один сильно убедителен,
другой слабо — confluence повышается.

**Стоимость:** +3 LLM calls на кандидата × 15 candidates = ~$0.30 на тик (deep model).
6 тиков/день × $0.30 ≈ $1.80/день, $54/мес. В рамках LLM_DAILY_BUDGET_USD.
**Эффект:** +20–40% accuracy по research.

### P3 — Post-hoc confidence calibration

**Сейчас (P3a — quick win):** shrinkage в `aggregator.py`:

```python
_CONFIDENCE_SHRINKAGE = 0.75
effective_confluence = raw_confluence * _CONFIDENCE_SHRINKAGE
```

**Через 50–100 outcomes (P3b):** изотоническая регрессия в
`scripts/research/calibrate_confidence.py`:

```python
from sklearn.isotonic import IsotonicRegression
# X = predicted_confluence, y = win (1 / 0)
iso = IsotonicRegression(out_of_bounds="clip").fit(X, y)
# pickle.dump(iso, "research/data/calibrator.pkl")
# Загружать в aggregator, применять к raw confluence
```

Мониторинг — Brier score в `research.db`. Если растёт — регенерить калибратор.

**Стоимость:** 30 минут shrinkage; день калибровки когда данные собрались.

### P4 — Devil's Advocate agent

**После P2.** После Trader-вердикта — отдельный LLM пытается **invalidate** setup.
Фокус на:
- Скрытые макро-риски (Fed, регулятор, новости).
- Liquidity traps (тонкая монета, ширина spread).
- Crowded trade (funding extreme, OI rocketing).

Если возвращает `critical_risks >= 2` → confluence -0.15.
Если `critical_risks == 0` → confluence +0.05.

**Стоимость:** +1 LLM call **только на signal-ready candidates** (после confluence
gate, не на все 15). ~3-5 кандидатов/тик. Незаметно по бюджету.

### P5 — Order-flow microstructure features

**Что добавить в screener** (`app/screener/indicators.py` + `evaluation.py`):
- `obi` = `(Σbids_5lvl - Σasks_5lvl) / (Σbids + Σasks)` — bid/ask imbalance
- `microprice` = `(bid_qty × ask_px + ask_qty × bid_px) / (bid_qty + ask_qty)` — better fair value
- `trade_intensity_4h` = count of trades / 4h period

Источник: CCXT `fetch_order_book` + `fetch_trades` (бесплатно, без upgrade
тарифов). Уже работает с Binance.

**Эффект на 4h** — слабый (microstructure лучше для intraday). **OBI** хорошо ловит
готовность к breakout-у. Стоит запустить и измерить через P1.

### P6 — Funding extreme as contrarian signal

Сейчас:
```python
funding_bias = "long_heavy" if funding > 0.15% else ...
```

Лучше — non-linear:
- `|funding| > 0.30%` (sustained 3+ bars) → **squeeze risk** (контрарный: long_heavy = bearish bias)
- `|funding| < 0.05%` → neutral
- между — directional

Добавить как фичу в `derivatives.py` analyst prompt + явно в `Devil's Advocate`.

**Стоимость:** 1 час, изменения в `screener/evaluation.py` + `analysts/derivatives.py`
+ prompt update.

### P7 — Multi-timeframe alignment (1h + 1w)

**Что добавить:**
- В `analyze_technical` подгружать 1h × 50 свечей + 1w × 50 свечей дополнительно.
- 1h — refine entry trigger (e.g., "wait for bullish 1h engulfing").
- 1w — HTF bias confirmation.
- В `TechnicalReport` новые поля: `htf_alignment: bool`, `entry_trigger_present: bool`.

**Стоимость:** 2–3 часа — правки в `agents/technical/levels.py`,
`prompts/technical.yaml`, `TechnicalReport` model.

### P8 — Setup-type-aware risk / leverage

Текущий `confidence_risk_pct` — линейный single-dimension. Лучше:
- Добавить `leverage_intent` в `CryptoSetup` (`conservative` / `moderate` / `aggressive`) — символьный intent от LLM.
- Маппинг `(setup_type, intent, macro_regime) → leverage` в Python (`app/portfolio/leverage.py`).
- Hard caps: `MAX_LEVERAGE` в `.env`.
- В `virtual_position` добавить `leverage: int`, `margin: Decimal`.

См. подробности в обсуждении с агентом (история чата 2026-05-27). LLM выбирает
**категорию агрессии**, число решает Python.

**Стоимость:** ~4 часа + alembic-миграция.

### P9 — Cross-position correlation awareness

**Проблема:** сейчас можем открыть 2 long на BTC-correlated alts (SOL + ETH) +
long на BTC — фактически тройной BTC bet.

**Что делать:**
- В `core/constants/correlation.py` — статический маппинг symbol → bucket
  (BTC-corr, ETH-corr, AI-tokens, memes, L1, DeFi…).
- Новый gate в `PortfolioManager`: `Decision.SKIPPED_CORRELATION`, если в bucket
  уже ≥ N открытых.
- Долгосрочно — поддерживать correlation matrix из rolling 30d returns (не
  захардкоженный bucket).

**Стоимость:** 3–4 часа для статической версии.

### P10 — Memory across ticks

**Что добавить:**
- Snapshot regime каждый тик в `system_state`.
- Macro analyst prompt получает `recent_regimes: list[3]` — историю последних трёх тиков.
- Если регим **меняется** (Trending → Ranging) — снизить агрессию на следующих
  тиках через корректировку `confluence_score`.

**Стоимость:** 2 часа prompt-engineering + минимум кода.

## 5. Очередность реализации

```
Спринт 1 (сейчас, foundation)
├── P1   Outcome tracking + features snapshot              [4ч]   MUST
├── P3a  Shrinkage 0.75 для confidence                     [30мин] quick win
└── P6   Funding extreme contrarian                        [1ч]   quick win

Спринт 2 (после 30+ закрытых сделок)
├── P2   Bull/Bear/Trader debate                           [день] biggest accuracy gain
├── P4   Devil's Advocate                                  [4ч]
└── P8   Setup-type-aware risk + leverage                  [4ч]

Спринт 3 (после 100+ outcomes)
├── P3b  Isotonic calibration                              [день]
├── P5   Order-flow features (OBI / microprice)            [4ч]
├── P7   Multi-timeframe alignment                         [4ч]
└── P9   Correlation awareness                             [4ч]

Спринт 4 (после 500+ outcomes)
└── Per-feature P&L attribution → перевзвешивание _WEIGHTS в aggregator (data-driven)
```

## 6. Anti-patterns / чего НЕ делать

- ❌ **Не лезть в Kelly criterion** до 100+ outcomes. Full Kelly = ruin при плохих
  оценках win rate. Stick с fixed fractional пока probability не калиброваны.
- ❌ **Не добавлять more analysts** (типа `OnChainAnalyst`) пока не работают
  существующие. Ширина без глубины.
- ❌ **Не пытаться заводить Bull/Bear debate до P1** — нечем измерить улучшение
  (нет outcome attribution).
- ❌ **Не покупать дорогие CoinGlass планы** (Heatmap, Max Pain) пока не доказан
  edge на дешёвых features.
- ❌ **Не переписывать на RL / transformer signal models** — академический хайп,
  годами в стадии proof-of-concept для crypto.
- ❌ **Не оптимизировать LLM-промпты до выкладки P1** — без attribution не
  узнаешь помог ли prompt change или ухудшил.

## 7. Open questions

- [ ] **Стоит ли** инвестировать в OnChain (CoinMetrics)? Для свежих токенов
  данных мало; для BTC/ETH данные хороши. Возможно — отложить до Спринта 3.
- [ ] **Какой horizon** для outcome (R-multiple): 1d, 3d, до stop/target?
  Текущий watcher закрывает по событиям — это правильный horizon, но нужно
  явно записать.
- [ ] **Win rate vs expectancy** — что приоритезируем? Для крипто-перпов
  expectancy важнее (асимметричные распределения).
- [ ] **Bull/Bear debate** — 2 round trips или 3? Больше = дороже + длиннее тик.
- [ ] **Cross-correlation** — статический bucket или rolling 30d?
- [ ] **Sentiment analyst** — стоит ли заменить LunarCrush на on-chain mention
  graph (Glassnode)? Дороже, но точнее для крипто-specific сетапов.

## 8. Метрики прогресса (что замерять чтобы понять что улучшения работают)

После каждого изменения замерять на 50+ outcomes:

| Метрика | Цель |
|---|---|
| Win rate (TAKEN signals) | > 50% |
| Expectancy (avg R-multiple) | > 0.3 |
| Brier score (confluence calibration) | < 0.20, идеал 0.12-0.15 |
| LLM cost per closed signal | < $0.10 |
| False-positive rate (signal_ready → SKIPPED_DRAWDOWN после) | < 10% |
| Setup-type concentration | < 50% в одном типе |
| Tick failure rate | < 5% |

## 9. Источники

- [TradingAgents arxiv 2412.20138](https://arxiv.org/pdf/2412.20138)
- [TauricResearch/TradingAgents GitHub](https://github.com/TauricResearch/TradingAgents)
- [TrustTrade arxiv 2603.22567](https://arxiv.org/pdf/2603.22567)
- [QuantAgent arxiv 2509.09995](https://arxiv.org/html/2509.09995v3)
- [LLM calibration arxiv 2512.16030](https://arxiv.org/html/2512.16030)
- [Latitude — Calibrating LLM Confidence](https://latitude.so/blog/5-methods-for-calibrating-llm-confidence-scores)
- [Altrady — Kelly for Crypto](https://www.altrady.com/blog/risk-management/kelly-criterion-crypto-position-sizing)
- [Kalena.ai — Liquidation Heatmap](https://blog.kalena.ai/liquidation-heatmap-where-leveraged-positions-go-to-die-and-how-smart-traders-get-there-first)
- [Atas — Order Flow Heatmap](https://atas.net/blog/heatmap/)
- [Visiion — Order Flow Crypto](https://blog.visiion.io/order-flow-trading-crypto-guide/)
- [Microstructure arxiv 2602.00776](https://arxiv.org/pdf/2602.00776)
