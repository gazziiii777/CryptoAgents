#!/usr/bin/env python
"""Атрибуция результата сделок: какие фичи/сетапы/режимы реально дают edge.

Использование:
    python -m scripts.research.attribution

Читает research-БД (trade_outcome + signal_record), считает по группам:
    - overall: n, win rate, avg R-multiple, total PnL, avg holding;
    - по setup_type;
    - по macro_regime;
    - по confluence-бакетам (0.1 ширина) — это датасет для калибровки (P3b):
      сравнивает заявленную confluence с фактическим win rate.

Это фундамент для обоснованных правок весов аналитиков, leverage-таблиц и
изотонической калибровки. Без накопленных outcome'ов отчёт будет пустым.
"""

import asyncio

from sqlalchemy import text

from db.research.engine import research_session_scope

_OVERALL = """
SELECT
  COUNT(*) AS n,
  SUM(realized_pnl > 0) AS wins,
  AVG(r_multiple) AS avg_r,
  SUM(realized_pnl) AS total_pnl,
  AVG(holding_hours) AS avg_hours
FROM trade_outcome
"""

_BY_SETUP = """
SELECT
  COALESCE(setup_type, 'unknown') AS grp,
  COUNT(*) AS n,
  SUM(realized_pnl > 0) AS wins,
  AVG(r_multiple) AS avg_r,
  SUM(realized_pnl) AS total_pnl
FROM trade_outcome
GROUP BY grp
ORDER BY n DESC
"""

_BY_REGIME = """
SELECT
  sr.macro_regime AS grp,
  COUNT(*) AS n,
  SUM(t.realized_pnl > 0) AS wins,
  AVG(t.r_multiple) AS avg_r,
  SUM(t.realized_pnl) AS total_pnl
FROM trade_outcome t
JOIN signal_record sr ON t.signal_record_id = sr.id
GROUP BY grp
ORDER BY n DESC
"""

_BY_CONFLUENCE = """
SELECT
  ROUND(FLOOR(sr.confluence_score * 10) / 10, 1) AS bucket,
  COUNT(*) AS n,
  SUM(t.realized_pnl > 0) AS wins,
  AVG(t.r_multiple) AS avg_r
FROM trade_outcome t
JOIN signal_record sr ON t.signal_record_id = sr.id
GROUP BY bucket
ORDER BY bucket
"""

_BY_EXIT = """
SELECT
  exit_reason AS grp,
  COUNT(*) AS n,
  AVG(r_multiple) AS avg_r,
  SUM(realized_pnl) AS total_pnl
FROM trade_outcome
GROUP BY grp
ORDER BY n DESC
"""

_BY_DIVERGENCE = """
SELECT
  COALESCE(sr.smart_money_divergence, 'unknown') AS grp,
  COUNT(*) AS n,
  SUM(t.realized_pnl > 0) AS wins,
  AVG(t.r_multiple) AS avg_r,
  SUM(t.realized_pnl) AS total_pnl
FROM trade_outcome t
JOIN signal_record sr ON t.signal_record_id = sr.id
GROUP BY grp
ORDER BY n DESC
"""

_BY_PUMP_RISK = """
SELECT
  COALESCE(sr.pump_risk, 'unknown') AS grp,
  COUNT(*) AS n,
  SUM(t.realized_pnl > 0) AS wins,
  AVG(t.r_multiple) AS avg_r,
  SUM(t.realized_pnl) AS total_pnl
FROM trade_outcome t
JOIN signal_record sr ON t.signal_record_id = sr.id
GROUP BY grp
ORDER BY n DESC
"""

_BY_TRADER_VERDICT = """
SELECT
  COALESCE(sr.trader_verdict, 'unknown') AS grp,
  COUNT(*) AS n,
  SUM(t.realized_pnl > 0) AS wins,
  AVG(t.r_multiple) AS avg_r,
  AVG(sr.trader_conviction) AS avg_conviction
FROM trade_outcome t
JOIN signal_record sr ON t.signal_record_id = sr.id
GROUP BY grp
ORDER BY n DESC
"""


def _win_rate(wins: int | None, n: int) -> float:
    return (wins or 0) / n if n else 0.0


def _fmt(value: float | None, spec: str) -> str:
    return format(value, spec) if value is not None else "n/a"


async def _fetch(sql: str) -> list[dict[str, object]]:
    async with research_session_scope() as session:
        result = await session.execute(text(sql))
        return [dict(row) for row in result.mappings().all()]


def _print_group(title: str, rows: list[dict[str, object]], group_key: str) -> None:
    print(f"\n=== {title} ===")
    if not rows:
        print("  (no data)")
        return
    print(f"  {'group':<20} {'n':>5} {'win%':>7} {'avgR':>7} {'pnl':>12}")
    for row in rows:
        n = int(row["n"])
        wr = _win_rate(row.get("wins"), n) * 100
        avg_r = row.get("avg_r")
        pnl = row.get("total_pnl")
        print(
            f"  {str(row[group_key]):<20} {n:>5} {wr:>6.1f}% "
            f"{_fmt(avg_r, '>7.2f')} {_fmt(pnl, '>12.2f')}"
        )


async def _main() -> None:
    overall = await _fetch(_OVERALL)
    row = overall[0] if overall else {}
    n = int(row.get("n") or 0)
    print("=== OVERALL ===")
    if n == 0:
        print("  No closed trades yet — attribution needs outcomes.")
        return
    print(f"  trades:       {n}")
    print(f"  win rate:     {_win_rate(row.get('wins'), n) * 100:.1f}%")
    print(f"  avg R:        {_fmt(row.get('avg_r'), '.2f')}")
    print(f"  total PnL:    {_fmt(row.get('total_pnl'), '.2f')}")
    print(f"  avg holding:  {_fmt(row.get('avg_hours'), '.1f')}h")

    _print_group("BY SETUP TYPE", await _fetch(_BY_SETUP), "grp")
    _print_group("BY MACRO REGIME", await _fetch(_BY_REGIME), "grp")
    _print_group("BY EXIT REASON", await _fetch(_BY_EXIT), "grp")
    _print_group("BY SMART-MONEY DIVERGENCE", await _fetch(_BY_DIVERGENCE), "grp")
    _print_group("BY PUMP RISK", await _fetch(_BY_PUMP_RISK), "grp")
    _print_group("BY TRADER VERDICT", await _fetch(_BY_TRADER_VERDICT), "grp")

    print("\n=== CONFLUENCE CALIBRATION (заявлено vs факт) ===")
    conf_rows = await _fetch(_BY_CONFLUENCE)
    if not conf_rows:
        print("  (no data)")
    else:
        print(f"  {'bucket':<10} {'n':>5} {'win%':>7} {'avgR':>7}")
        for cr in conf_rows:
            cn = int(cr["n"])
            print(
                f"  {_fmt(cr['bucket'], '<10.1f')} {cn:>5} "
                f"{_win_rate(cr.get('wins'), cn) * 100:>6.1f}% "
                f"{_fmt(cr.get('avg_r'), '>7.2f')}"
            )
        print(
            "\n  Если win% существенно ниже bucket'а — LLM overconfident, "
            "подкрути CONFIDENCE_SHRINKAGE или подключи изотоническую калибровку (P3b)."
        )


if __name__ == "__main__":
    asyncio.run(_main())
