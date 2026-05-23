#!/usr/bin/env python
"""Скачивает исторические данные по топ-N перп-парам для калибровки сигналов.

Использование:
    python scripts/research/collect_data.py [--symbols N] [--days N] [--refresh]

Выходные файлы: scripts/scripts/research/data/<SYMBOL>.parquet (один файл на монету)
Колонки: open, high, low, close, volume, funding_rate, open_interest,
         long_short_ratio, vol_delta
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

from core import settings  # noqa: E402
from app.clients.binance_client import BinanceClient  # noqa: E402
from app.clients.ccxt_client import CcxtClient, make_exchange  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("collect_data")

_DATA_DIR = _ROOT / "research" / "data"


async def _build_universe(n: int, min_volume_usd: float) -> list[str]:
    """Перп-USDT пары по суточному объёму: фильтр по min_volume_usd, топ-N по объёму."""
    exchange = make_exchange()
    try:
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
    finally:
        await exchange.close()

    perps = [
        s
        for s, m in exchange.markets.items()
        if m.get("swap")
        and m.get("quote") == "USDT"
        and s in tickers
        and float(tickers[s].get("quoteVolume") or 0) >= min_volume_usd
    ]
    return sorted(
        perps, key=lambda s: float(tickers[s].get("quoteVolume") or 0), reverse=True
    )[:n]


def _out_path(symbol: str) -> Path:
    return _DATA_DIR / f"{symbol.replace('/', '_').replace(':', '_')}.parquet"


async def _collect_one(
    symbol: str,
    ccxt_client: CcxtClient,
    binance_client: BinanceClient,
    days: int,
    refresh: bool,
    sem: asyncio.Semaphore,
) -> None:
    out = _out_path(symbol)
    if out.exists() and not refresh:
        logger.info("skip %s (cached)", symbol)
        return

    async with sem:
        logger.info("fetching %s ...", symbol)
        try:
            candle_limit = min(days * 6 + 150, 1500)
            oi_limit = min(days * 6, 500)

            candles_4h, funding_hist = await asyncio.gather(
                ccxt_client.fetch_ohlcv(symbol, timeframe="4h", limit=candle_limit),
                ccxt_client.fetch_funding_rate_history(
                    symbol, limit=min(days * 3, 500)
                ),
            )
            oi_hist, ls_hist, cvd_points = await asyncio.gather(
                binance_client.fetch_open_interest_history(
                    symbol, period="4h", limit=oi_limit
                ),
                binance_client.fetch_long_short_ratio(
                    symbol, period="4h", limit=oi_limit
                ),
                binance_client.fetch_cvd(symbol, num_candles=min(days * 6, 1500)),
            )
        except Exception:
            logger.warning("fetch failed for %s", symbol, exc_info=True)
            return

    df = pd.DataFrame([c.model_dump() for c in candles_4h]).set_index("timestamp")
    df.index = df.index.astype("int64")

    if funding_hist:
        fr = pd.DataFrame([e.model_dump() for e in funding_hist]).set_index(
            "timestamp"
        )["funding_rate"]
        fr.index = fr.index.astype("int64")
        df["funding_rate"] = fr.reindex(df.index, method="ffill")
    else:
        df["funding_rate"] = float("nan")

    if oi_hist:
        oi = pd.DataFrame([s.model_dump() for s in oi_hist]).set_index("timestamp")[
            "open_interest"
        ]
        oi.index = oi.index.astype("int64")
        df["open_interest"] = oi.reindex(df.index, method="nearest")
    else:
        df["open_interest"] = float("nan")

    if ls_hist:
        ls = pd.DataFrame([r.model_dump() for r in ls_hist]).set_index("timestamp")[
            "long_short_ratio"
        ]
        ls.index = ls.index.astype("int64")
        df["long_short_ratio"] = ls.reindex(df.index, method="nearest")
    else:
        df["long_short_ratio"] = float("nan")

    if len(cvd_points) >= 2:
        ts = [p.timestamp for p in cvd_points]
        cvds = [p.cvd for p in cvd_points]
        deltas = [cvds[0]] + [cvds[i] - cvds[i - 1] for i in range(1, len(cvds))]
        vd = pd.Series(deltas, index=pd.Index(ts, dtype="int64"))
        df["vol_delta"] = vd.reindex(df.index, method="nearest")
    else:
        df["vol_delta"] = float("nan")

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    logger.info("saved %s → %d rows", symbol, len(df))


async def main(symbols: int, days: int, refresh: bool, min_volume_usd: float) -> None:
    logger.info(
        "loading universe (top %d, min_volume=$%.0fM) ...",
        symbols,
        min_volume_usd / 1_000_000,
    )
    universe = await _build_universe(symbols, min_volume_usd)
    logger.info("%d symbols found", len(universe))

    sem = asyncio.Semaphore(5)
    async with BinanceClient() as binance_client:
        async with CcxtClient() as ccxt_client:
            await asyncio.gather(*[
                _collect_one(s, ccxt_client, binance_client, days, refresh, sem)
                for s in universe
            ])
    logger.info("collection complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--symbols",
        type=int,
        default=200,
        metavar="N",
        help="max symbols to collect after volume filter (default: 200)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        metavar="N",
        help="days of history per symbol (default: 90)",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=settings.UNIVERSE_MIN_VOLUME_USD,
        metavar="USD",
        help=f"min 24h quote volume in USD (default: {settings.UNIVERSE_MIN_VOLUME_USD:,.0f})",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download even if parquet already exists",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            symbols=args.symbols,
            days=args.days,
            refresh=args.refresh,
            min_volume_usd=args.min_volume,
        )
    )
