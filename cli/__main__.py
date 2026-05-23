from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from app.logger import setup_logging  # noqa: E402
from cli.commands import db, enrich, keys_check, lc_test, screener, selftest  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli",
        description=(
            "TradingAgents CLI. Subcommands run individual stages of the pipeline "
            "(screener, enrich) or diagnostic helpers (keys-check, lc-test). "
            "Use --mock on enrich to skip HTTP and exercise the module on fixed data."
        ),
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="DEBUG-level logging"
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    keys_check.register(sub)
    screener.register(sub)
    enrich.register(sub)
    lc_test.register(sub)
    selftest.register(sub)
    db.register(sub)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    try:
        result = args.handler(args)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
