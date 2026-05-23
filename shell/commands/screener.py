from __future__ import annotations

import argparse

from app.screener.screener import run_screener


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "screener",
        help="Run the screener stage only. Prints top-N candidates with signals.",
    )
    p.set_defaults(handler=_handle)


async def _handle(_args: argparse.Namespace) -> None:
    results = await run_screener()
    print(f"\nScreener returned {len(results)} candidates:\n")
    for r in results:
        s = r.signals
        print(
            f"  [{r.score}] {r.symbol:<22} dir={r.direction:<6} adx={r.adx:.1f}  "
            f"trend={s.daily_trend:<8} rsi={s.rsi_level or 0:.0f}  "
            f"funding={s.funding_rate:.4f}  oi_chg={s.oi_change_4h_pct * 100:+.1f}%"
        )
