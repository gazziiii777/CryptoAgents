from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.logger import setup_logging  # noqa: E402
from app.screener.screener import run_screener  # noqa: E402

setup_logging(logging.INFO)
logger = logging.getLogger(__name__)

_CALIBRATION_MAX_AGE_DAYS = 90


def _warn_if_calibration_stale() -> None:
    data_dir = Path(__file__).parent / "research" / "data"
    files = list(data_dir.glob("*.parquet"))
    if not files:
        logger.warning("No calibration data. Run: python research/calibrate.py")
        return
    age_days = (time.time() - min(f.stat().st_mtime for f in files)) / 86400
    if age_days > _CALIBRATION_MAX_AGE_DAYS:
        logger.warning(
            "Calibration data is %.0f days old — thresholds may be stale. "
            "Run: python research/calibrate.py",
            age_days,
        )


async def _main() -> None:
    _warn_if_calibration_stale()
    results = await run_screener()

    logger.info("═" * 60)
    logger.info("SCREENER RESULTS — top %d", len(results))
    logger.info("═" * 60)

    for r in results:
        sig = r.signals
        logger.info(
            "[%d] %s  adx=%.1f  trend=%s  rsi=%.0f  funding=%.4f  oi_chg=%.1f%%  ls_retail=%.2f  ls_top=%.2f",
            r.score,
            r.symbol,
            r.adx,
            sig.daily_trend,
            sig.rsi_level or 0.0,
            sig.funding_rate,
            sig.oi_change_4h_pct * 100,
            sig.long_short_ratio or 0.0,
            sig.top_trader_ls_ratio or 0.0,
        )
        active = [
            k
            for k, v in {
                "vol_spike": sig.volume_spike,
                "bb_squeeze": sig.bb_squeeze,
                "near_swing": sig.near_swing,
                "ema_cross": sig.ema_cross,
                "rsi_div": sig.rsi_divergence,
                "macd": sig.macd,
                "cvd_div": sig.cvd_price_divergence,
                "liq_spike": sig.liq_spike,
            }.items()
            if v
        ]
        logger.info("    signals: %s", ", ".join(active) if active else "—")

    logger.info("═" * 60)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
