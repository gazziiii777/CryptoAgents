#!/usr/bin/env python
"""Вычисляет cross-sectional IC, ICIR и decay-кривые сигналов; подбирает пороги.

Использование:
    python scripts/research/analyze.py [--forward-hours N] [--data DIR]

Выходные файлы:
    scripts/research/report.txt                   -- текстовый отчёт
    scripts/research/recommended_thresholds.json  -- рекомендуемые настройки для settings.py

Методология:
    Cross-sectional Spearman IC — в каждый момент t ранжирует все символы по сигналу
    и коррелирует с форвардной доходностью. Один IC на период → усредняем по времени.
    Это прямой ответ на вопрос "правильно ли сигнал ранжирует монеты прямо сейчас?"

    IS/OOS split: пороги подбираются на первых 70% данных (IS), OOS IC — на последних 30%.
    Это минимальная защита от overfit при threshold sweep.

    ICIR = mean_IC / std_IC — надёжнее сырого IC: учитывает стабильность сигнала.
    IC decay — IC при горизонтах 4h..96h: показывает halflife предсказательной силы.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
import ta
from scipy import stats

_ROOT = Path(__file__).parent.parent
_DATA_DIR = _ROOT / "research" / "data"
_REPORT_PATH = _ROOT / "research" / "report.txt"
_JSON_PATH = _ROOT / "research" / "recommended_thresholds.json"

_BASE_CFG: dict[str, float] = {
    "RSI_OVERBOUGHT": 70.0,
    "RSI_OVERSOLD": 30.0,
    "VOLUME_SPIKE_MULTIPLIER": 2.0,
    "BB_SQUEEZE_THRESHOLD": 0.06,
    "FUNDING_RATE_HIGH": 0.0008,
    "FUNDING_RATE_LOW": -0.0005,
    "OI_TREND_MIN_PCT": 0.15,
    "LS_RATIO_HIGH": 2.2,
    "LS_RATIO_LOW": 0.55,
}

_SIGNAL_NAMES: dict[str, str] = {
    "sig_rsi": "RSI extreme",
    "sig_macd": "MACD dir",
    "sig_ema": "EMA cross",
    "sig_trend": "EMA trend",
    "sig_vol_spike": "Volume spike",
    "sig_bb_squeeze": "BB squeeze",
    "sig_funding": "Funding bias",
    "sig_oi": "OI change",
    "sig_ls": "L/S ratio",
    "sig_cvd": "CVD trend",
}

_DECAY_HORIZONS = [1, 2, 4, 8, 12, 24]

_OOS_FRACTION = 0.30
_MIN_ASSETS_PER_PERIOD = 5


class ICStats(NamedTuple):
    mean_ic: float
    std_ic: float
    icir: float
    t_stat: float
    n_periods: int
    hit_rate: float
    oos_mean_ic: float


class SweepRow(NamedTuple):
    value: float
    ic: float
    icir: float
    hit_rate: float
    n_obs: int


def _load_all(data_dir: Path) -> list[tuple[str, pd.DataFrame]]:
    files = sorted(data_dir.glob("*.parquet"))
    if not files:
        print(
            f"No parquet files in {data_dir}. Run collect_data.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    result = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            df.index = df.index.astype("int64")
            result.append((f.stem, df))
        except Exception as e:
            print(f"WARNING: skipping {f.name}: {e}", file=sys.stderr)

    print(f"Loaded {len(result)} symbols from {data_dir}")
    return result


def _compute_signals(df: pd.DataFrame, cfg: dict[str, float]) -> pd.DataFrame:
    """Добавляет sig_* колонки (-1=short, 0=neutral, 1=long) к DataFrame с OHLCV."""
    out = df.copy()

    rsi = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    out["sig_rsi"] = pd.Series(
        np.where(
            rsi <= cfg["RSI_OVERSOLD"], 1, np.where(rsi >= cfg["RSI_OVERBOUGHT"], -1, 0)
        ),
        index=df.index,
    )

    hist = ta.trend.MACD(df["close"]).macd_diff()
    out["sig_macd"] = pd.Series(
        np.where(
            (hist > 0) & (hist > hist.shift(1)),
            1,
            np.where((hist < 0) & (hist < hist.shift(1)), -1, 0),
        ),
        index=df.index,
    )

    ema20 = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    cross = ema20 - ema50
    out["sig_ema"] = pd.Series(
        np.where(
            (cross.shift(1) < 0) & (cross >= 0),
            1,
            np.where((cross.shift(1) > 0) & (cross <= 0), -1, 0),
        ),
        index=df.index,
    )
    out["sig_trend"] = pd.Series(
        np.where(ema20 > ema50, 1, np.where(ema20 < ema50, -1, 0)), index=df.index
    )

    vol_sma = df["volume"].rolling(20).mean().shift(1)
    out["sig_vol_spike"] = pd.Series(
        np.where(df["volume"] > cfg["VOLUME_SPIKE_MULTIPLIER"] * vol_sma, 1, 0),
        index=df.index,
    )

    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2.0)
    bb_mid = bb.bollinger_mavg().replace(0, np.nan)
    bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / bb_mid
    out["sig_bb_squeeze"] = pd.Series(
        np.where(bb_width < cfg["BB_SQUEEZE_THRESHOLD"], 1, 0), index=df.index
    )

    if "funding_rate" in df.columns:
        fr = df["funding_rate"]
        out["sig_funding"] = pd.Series(
            np.where(
                fr >= cfg["FUNDING_RATE_HIGH"],
                -1,
                np.where(fr <= cfg["FUNDING_RATE_LOW"], 1, 0),
            ),
            index=df.index,
        )
    else:
        out["sig_funding"] = 0

    if "open_interest" in df.columns:
        oi_chg = df["open_interest"].pct_change(8)
        out["sig_oi"] = pd.Series(
            np.where(
                oi_chg >= cfg["OI_TREND_MIN_PCT"],
                1,
                np.where(oi_chg <= -cfg["OI_TREND_MIN_PCT"], -1, 0),
            ),
            index=df.index,
        )
    else:
        out["sig_oi"] = 0

    if "long_short_ratio" in df.columns:
        ls = df["long_short_ratio"]
        out["sig_ls"] = pd.Series(
            np.where(
                ls >= cfg["LS_RATIO_HIGH"],
                -1,
                np.where(ls <= cfg["LS_RATIO_LOW"], 1, 0),
            ),
            index=df.index,
        )
    else:
        out["sig_ls"] = 0

    if "vol_delta" in df.columns:
        cvd_roll = df["vol_delta"].rolling(8).sum()
        out["sig_cvd"] = pd.Series(
            np.where(cvd_roll > 0, 1, np.where(cvd_roll < 0, -1, 0)), index=df.index
        )
    else:
        out["sig_cvd"] = 0

    return out


def _build_panels(
    symbols: list[tuple[str, pd.DataFrame]], cfg: dict[str, float]
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Строит кросс-секциональные панели для всех сигналов и цен закрытия.

    Возвращает:
        signal_panels: {sig_col: DataFrame(index=timestamp, columns=symbol_name)}
        close_panel:   DataFrame(index=timestamp, columns=symbol_name)
    """
    sig_cols = list(_SIGNAL_NAMES.keys())
    sig_dicts: dict[str, dict[str, pd.Series]] = {c: {} for c in sig_cols}
    close_dict: dict[str, pd.Series] = {}

    for name, df in symbols:
        df_sig = _compute_signals(df, cfg)
        close_dict[name] = df_sig["close"]
        for col in sig_cols:
            sig_dicts[col][name] = df_sig[col]

    signal_panels = {col: pd.DataFrame(sig_dicts[col]) for col in sig_cols}
    close_panel = pd.DataFrame(close_dict)
    return signal_panels, close_panel


def _cs_ic_series(sig_panel: pd.DataFrame, fwd_panel: pd.DataFrame) -> pd.Series:
    """
    Cross-sectional Spearman IC в каждый момент времени.

    В момент t: corr(сигналы по символам, форвардная доходность по символам).
    Пропускает периоды с менее чем _MIN_ASSETS_PER_PERIOD валидными парами.
    """
    common = sig_panel.index.intersection(fwd_panel.index)
    ics: dict[int, float] = {}
    for ts in common:
        sig = sig_panel.loc[ts]
        fwd = fwd_panel.loc[ts]
        mask = sig.notna() & fwd.notna() & (sig != 0)
        if mask.sum() < _MIN_ASSETS_PER_PERIOD:
            continue
        ic, _ = stats.spearmanr(sig[mask], fwd[mask])
        if not np.isnan(ic):
            ics[int(ts)] = float(ic)
    return pd.Series(ics)


def _ic_stats(
    ic_series: pd.Series, sig_panel: pd.DataFrame, oos_index: pd.Index
) -> ICStats:
    if ic_series.empty:
        return ICStats(0.0, 0.0, 0.0, 0.0, 0, 0.0, float("nan"))

    mean_ic = float(ic_series.mean())
    std_ic = float(ic_series.std())
    icir = mean_ic / std_ic if std_ic > 0 else 0.0
    t_stat = icir * math.sqrt(len(ic_series))

    oos_ic_vals = ic_series[ic_series.index.isin(oos_index)]
    oos_mean_ic = float(oos_ic_vals.mean()) if not oos_ic_vals.empty else float("nan")

    fires_any = (sig_panel != 0).any(axis=1)
    hit_rate = float(fires_any.sum()) / max(len(sig_panel), 1)

    return ICStats(
        mean_ic=mean_ic,
        std_ic=std_ic,
        icir=icir,
        t_stat=t_stat,
        n_periods=len(ic_series),
        hit_rate=hit_rate,
        oos_mean_ic=oos_mean_ic,
    )


def _ts_split(close_panel: pd.DataFrame) -> tuple[pd.Index, pd.Index]:
    """Разбивает временной индекс на IS (70%) и OOS (30%) по времени."""
    all_ts = sorted(close_panel.index.tolist())
    split = int(len(all_ts) * (1 - _OOS_FRACTION))
    return pd.Index(all_ts[:split]), pd.Index(all_ts[split:])


def _compute_ic_table(
    signal_panels: dict[str, pd.DataFrame], close_panel: pd.DataFrame, fwd_periods: int
) -> dict[str, ICStats]:
    """Cross-sectional IC для всех сигналов с разбивкой IS/OOS."""
    fwd_panel = close_panel.pct_change(-fwd_periods)
    is_idx, oos_idx = _ts_split(close_panel)

    result: dict[str, ICStats] = {}
    for col, sig_panel in signal_panels.items():
        sig_is = sig_panel.loc[sig_panel.index.isin(is_idx)]
        fwd_is = fwd_panel.loc[fwd_panel.index.isin(is_idx)]
        ic_series = _cs_ic_series(sig_is, fwd_is)

        sig_oos = sig_panel.loc[sig_panel.index.isin(oos_idx)]
        fwd_oos = fwd_panel.loc[fwd_panel.index.isin(oos_idx)]
        oos_series = _cs_ic_series(sig_oos, fwd_oos)

        stats_obj = _ic_stats(ic_series, sig_panel, oos_idx)
        oos_mean = float(oos_series.mean()) if not oos_series.empty else float("nan")
        result[col] = stats_obj._replace(oos_mean_ic=oos_mean)

    return result


def _compute_ic_decay(
    signal_panels: dict[str, pd.DataFrame],
    close_panel: pd.DataFrame,
    horizons: list[int],
) -> dict[str, list[float]]:
    """IC при каждом горизонте из horizons (в барах). Использует все данные."""
    decay: dict[str, list[float]] = {col: [] for col in signal_panels}
    for h in horizons:
        fwd_panel = close_panel.pct_change(-h)
        for col, sig_panel in signal_panels.items():
            ic_series = _cs_ic_series(sig_panel, fwd_panel)
            decay[col].append(float(ic_series.mean()) if not ic_series.empty else 0.0)
    return decay


def _sweep_threshold(
    symbols: list[tuple[str, pd.DataFrame]],
    close_panel: pd.DataFrame,
    fwd_periods: int,
    base_cfg: dict[str, float],
    param: str,
    signal_col: str,
    values: list[float],
    is_idx: pd.Index,
) -> list[SweepRow]:
    """Перебор порогов на IS-данных. close_panel передаётся снаружи для переиспользования."""
    fwd_panel = close_panel.pct_change(-fwd_periods)
    fwd_is = fwd_panel.loc[fwd_panel.index.isin(is_idx)]

    rows = []
    for v in values:
        cfg = {**base_cfg, param: v}
        sig_dict = {name: _compute_signals(df, cfg)[signal_col] for name, df in symbols}
        sig_panel = pd.DataFrame(sig_dict)
        sig_is = sig_panel.loc[sig_panel.index.isin(is_idx)]

        ic_series = _cs_ic_series(sig_is, fwd_is)
        mean_ic = float(ic_series.mean()) if not ic_series.empty else 0.0
        std_ic = float(ic_series.std()) if not ic_series.empty else 0.0
        icir = mean_ic / std_ic if std_ic > 0 else 0.0

        fires = (sig_is != 0).any(axis=1)
        rows.append(
            SweepRow(
                value=v,
                ic=mean_ic,
                icir=icir,
                hit_rate=float(fires.sum()) / max(len(sig_is), 1),
                n_obs=int(fires.sum()),
            )
        )
    return rows


def _best_threshold(rows: list[SweepRow], min_hit_rate: float = 0.01) -> SweepRow:
    viable = [r for r in rows if r.hit_rate >= min_hit_rate]
    pool = viable if viable else rows
    return max(pool, key=lambda r: abs(r.icir) if r.icir != 0.0 else abs(r.ic))


def _halflife_str(decay_vals: list[float], horizons: list[int]) -> str:
    if not decay_vals:
        return "n/a"
    peak = abs(decay_vals[0])
    if peak < 1e-6:
        return "n/a"
    for h, v in zip(horizons[1:], decay_vals[1:]):
        if abs(v) <= peak * 0.5:
            return f"~{h * 4}h"
    return f">{horizons[-1] * 4}h"


def _format_report(
    ic_table: dict[str, ICStats],
    decay: dict[str, list[float]],
    sweeps: dict[str, list[SweepRow]],
    recommendations: dict[str, float],
    fwd_hours: int,
) -> str:
    lines: list[str] = []

    lines.append(f"=== Cross-Sectional IC Report  (forward_hours={fwd_hours}) ===")
    lines.append(
        f"IS = first {int((1 - _OOS_FRACTION) * 100)}%  |  OOS = last {int(_OOS_FRACTION * 100)}%  |  ICIR > 0.5 = acceptable, > 1.0 = strong\n"
    )
    lines.append(
        f"{'Signal':<22} {'IC_IS':>7} {'ICIR':>6} {'t_stat':>7} {'IC_OOS':>8} {'hit_rt':>7}  sig"
    )
    lines.append("-" * 70)

    for col, s in sorted(ic_table.items(), key=lambda x: -abs(x[1].icir)):
        name = _SIGNAL_NAMES.get(col, col)
        stars = (
            "***"
            if abs(s.t_stat) > 2.5
            else ("**" if abs(s.t_stat) > 2.0 else ("*" if abs(s.t_stat) > 1.5 else ""))
        )
        oos_str = (
            f"{s.oos_mean_ic:>+8.4f}" if not math.isnan(s.oos_mean_ic) else "     n/a"
        )
        lines.append(
            f"{name:<22} {s.mean_ic:>+7.4f} {s.icir:>6.3f} {s.t_stat:>7.2f} {oos_str} {s.hit_rate:>7.1%}  {stars}"
        )

    lines.append("\n*** |t|>2.5  ** |t|>2.0  * |t|>1.5  |  t = ICIR × √(n_periods)")
    lines.append("Positive IC_OOS close to IC_IS = signal is not overfit to IS period.")

    lines.append("\n\n=== IC Decay  (halflife of predictive power, bar = 4h) ===")
    horizons_label = "  ".join(f"{h * 4:>5}h" for h in _DECAY_HORIZONS)
    lines.append(f"{'Signal':<22} {horizons_label}  halflife")
    lines.append("-" * (22 + 8 * len(_DECAY_HORIZONS) + 12))

    for col in sorted(
        decay.keys(), key=lambda c: -abs(ic_table[c].mean_ic) if c in ic_table else 0
    ):
        name = _SIGNAL_NAMES.get(col, col)
        hl = _halflife_str(decay[col], _DECAY_HORIZONS)
        row_vals = "  ".join(f"{v:>+6.3f}" for v in decay[col])
        lines.append(f"{name:<22} {row_vals}  {hl}")

    lines.append(
        "Use halflife to choose rebalancing frequency: rebalance at ~halflife intervals."
    )

    lines.append(
        f"\n\n=== Threshold Sweep  (IS data only, first {int((1 - _OOS_FRACTION) * 100)}%) ===\n"
    )
    for param, rows in sweeps.items():
        lines.append(f"{param}:")
        for r in rows:
            tag = (
                " ← recommended"
                if abs(r.value - recommendations.get(param, -1)) < 1e-9
                else ""
            )
            lines.append(
                f"  {r.value:>9.5f}  IC={r.ic:>+7.4f}  ICIR={r.icir:>+6.3f}  hits={r.hit_rate:.1%}  n={r.n_obs:>5}{tag}"
            )
        lines.append("")

    lines.append("=== Recommended Thresholds ===\n")
    lines.append(json.dumps(recommendations, indent=2))
    lines.append(
        "\nWARNING: thresholds chosen on IS data only. Check IC_OOS before applying."
    )
    lines.append("Copy relevant values into core/settings.py.")
    return "\n".join(lines)


def main(fwd_hours: int, data_dir: Path) -> None:
    symbols = _load_all(data_dir)
    fwd_periods = fwd_hours // 4

    print("Building signal panels ...")
    signal_panels, close_panel = _build_panels(symbols, _BASE_CFG)
    is_idx, _ = _ts_split(close_panel)

    print("Computing cross-sectional IC table (IS/OOS split) ...")
    ic_table = _compute_ic_table(signal_panels, close_panel, fwd_periods)

    print("Computing IC decay curves ...")
    decay = _compute_ic_decay(signal_panels, close_panel, _DECAY_HORIZONS)

    sweep_specs: list[tuple[str, str, list[float]]] = [
        (
            "BB_SQUEEZE_THRESHOLD",
            "sig_bb_squeeze",
            [round(v, 3) for v in np.arange(0.02, 0.16, 0.01).tolist()],
        ),
        (
            "FUNDING_RATE_HIGH",
            "sig_funding",
            [round(v, 5) for v in np.arange(0.0003, 0.0021, 0.0001).tolist()],
        ),
        (
            "OI_TREND_MIN_PCT",
            "sig_oi",
            [round(v, 3) for v in np.arange(0.05, 0.31, 0.025).tolist()],
        ),
        (
            "VOLUME_SPIKE_MULTIPLIER",
            "sig_vol_spike",
            [round(v, 1) for v in np.arange(1.5, 4.1, 0.5).tolist()],
        ),
        (
            "LS_RATIO_HIGH",
            "sig_ls",
            [round(v, 1) for v in np.arange(1.5, 3.6, 0.1).tolist()],
        ),
    ]

    print("Sweeping thresholds on IS data ...")
    sweeps: dict[str, list[SweepRow]] = {}
    recommendations: dict[str, float] = dict(_BASE_CFG)

    for param, signal_col, values in sweep_specs:
        rows = _sweep_threshold(
            symbols,
            close_panel,
            fwd_periods,
            _BASE_CFG,
            param,
            signal_col,
            values,
            is_idx,
        )
        sweeps[param] = rows
        best = _best_threshold(rows)
        recommendations[param] = best.value
        print(
            f"  {param}: {_BASE_CFG[param]} → {best.value}  (IC={best.ic:+.4f}  ICIR={best.icir:+.3f}  hits={best.hit_rate:.1%})"
        )

    report = _format_report(ic_table, decay, sweeps, recommendations, fwd_hours)
    print("\n" + report)

    _REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nSaved: {_REPORT_PATH}")

    _JSON_PATH.write_text(json.dumps(recommendations, indent=2), encoding="utf-8")
    print(f"Saved: {_JSON_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--forward-hours",
        type=int,
        default=12,
        metavar="N",
        help="forward return horizon in hours, must be multiple of 4 (default: 12)",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=_DATA_DIR,
        metavar="DIR",
        help="directory with parquet files (default: scripts/research/data)",
    )
    args = parser.parse_args()
    if args.forward_hours % 4 != 0:
        print("ERROR: --forward-hours must be a multiple of 4", file=sys.stderr)
        sys.exit(1)
    main(fwd_hours=args.forward_hours, data_dir=args.data)
