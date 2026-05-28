#!/usr/bin/env python
"""Запускает полный цикл калибровки если данные устарели.

Использование:
    python scripts/research/calibrate.py               # запуск если данные > 90 дней
    python scripts/research/calibrate.py --force       # принудительный перезапуск
    python scripts/research/calibrate.py --check-only  # только статус, без запуска
    python scripts/research/calibrate.py --max-age-days 60

Cron (ежемесячно, 3-е число в 3:00):
    0 3 3 * * cd /path/to/TradingAgents && python scripts/research/calibrate.py >> scripts/research/calibrate.log 2>&1
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from core.constants.time import SECONDS_PER_DAY

_ROOT = Path(__file__).parent.parent
_DATA_DIR = _ROOT / "research" / "data"
_JSON_PATH = _ROOT / "research" / "recommended_thresholds.json"

_DEFAULT_MAX_AGE_DAYS = 90


def data_age_days() -> float | None:
    """Возраст самого старого parquet-файла в днях. None если данных нет."""
    files = list(_DATA_DIR.glob("*.parquet"))
    if not files:
        return None
    oldest_mtime = min(f.stat().st_mtime for f in files)
    return (time.time() - oldest_mtime) / SECONDS_PER_DAY


def needs_calibration(max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> bool:
    age = data_age_days()
    return age is None or age > max_age_days


def run_calibration() -> None:
    python = sys.executable
    subprocess.run(
        [python, str(_ROOT / "research" / "collect_data.py"), "--refresh"],
        cwd=str(_ROOT),
        check=True,
    )
    subprocess.run(
        [python, str(_ROOT / "research" / "analyze.py")], cwd=str(_ROOT), check=True
    )


def print_status() -> None:
    age = data_age_days()
    if age is None:
        print("status: NO DATA — calibration required")
        return
    thresholds_ok = _JSON_PATH.exists()
    print(
        f"status: data age = {age:.1f} days | thresholds.json = {'ok' if thresholds_ok else 'missing'}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=_DEFAULT_MAX_AGE_DAYS,
        metavar="N",
        help=f"re-run if data is older than N days (default: {_DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument(
        "--force", action="store_true", help="run regardless of data age"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="print status and exit (exit code 1 if calibration needed)",
    )
    args = parser.parse_args()

    if args.check_only:
        print_status()
        sys.exit(1 if needs_calibration(args.max_age_days) else 0)

    if args.force or needs_calibration(args.max_age_days):
        age = data_age_days()
        reason = "no data" if age is None else f"data is {age:.0f} days old"
        print(f"Starting calibration ({reason}) ...")
        run_calibration()
        print("Calibration complete.")
    else:
        print(
            f"Calibration is fresh ({data_age_days():.0f}d old). Use --force to re-run."
        )
