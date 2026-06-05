import asyncio
import logging
import time
from pathlib import Path

from dotenv import load_dotenv

from core.constants.time import SECONDS_PER_DAY

load_dotenv()

from app.logger import setup_logging  # noqa: E402
from app.engines.worker.pipeline.runner import run_pipeline  # noqa: E402

logger = logging.getLogger(__name__)

_CALIBRATION_MAX_AGE_DAYS = 90


def _warn_if_calibration_stale() -> None:
    data_dir = Path(__file__).parent / "scripts" / "research" / "data"
    files = list(data_dir.glob("*.parquet"))
    if not files:
        logger.warning("No calibration data. Run: python scripts/research/calibrate.py")
        return
    age_days = (time.time() - min(f.stat().st_mtime for f in files)) / SECONDS_PER_DAY
    if age_days > _CALIBRATION_MAX_AGE_DAYS:
        logger.warning(
            "Calibration data is %.0f days old — thresholds may be stale. "
            "Run: python scripts/research/calibrate.py",
            age_days,
        )


async def _run() -> None:
    _warn_if_calibration_stale()
    await run_pipeline()


def main() -> None:
    setup_logging(logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
