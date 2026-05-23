from __future__ import annotations

import argparse

from app.core import settings


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "keys-check",
        help="Show which API keys are configured (without printing values).",
    )
    p.set_defaults(handler=_handle)


def _mask(value: str) -> str:
    if not value:
        return "—"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


def _handle(_args: argparse.Namespace) -> None:
    rows = [
        ("LUNARCRUSH_API_KEY", settings.LUNARCRUSH_API_KEY, "required"),
        ("COINGLASS_API_KEY", settings.COINGLASS_API_KEY, "required"),
        ("COINGECKO_API_KEY", settings.COINGECKO_API_KEY, "optional"),
    ]
    print(f"{'KEY':<22} {'STATUS':<10} {'NECESSITY':<10} {'VALUE'}")
    print("-" * 60)
    for name, value, necessity in rows:
        status = "set" if value else "MISSING"
        print(f"{name:<22} {status:<10} {necessity:<10} {_mask(value)}")
