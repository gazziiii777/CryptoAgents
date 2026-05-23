from __future__ import annotations

import argparse
import json
from typing import Literal

from app.clients._symbols import normalized_base
from app.clients.lunarcrush_client import LunarCrushClient

Endpoint = Literal["list", "whatsup", "news", "posts", "time_series"]
_ENDPOINT_CHOICES: tuple[Endpoint, ...] = (
    "list",
    "whatsup",
    "news",
    "posts",
    "time_series",
)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "lc-test",
        help=(
            "Hit one LunarCrush endpoint with the configured key. "
            "Useful to verify plan access (Hobby/Individual/Builder) and key validity."
        ),
    )
    p.add_argument(
        "--endpoint",
        choices=_ENDPOINT_CHOICES,
        required=True,
        help="Which LC endpoint to call.",
    )
    p.add_argument(
        "--symbol",
        default="BTC/USDT:USDT",
        help=(
            "ccxt-style symbol (e.g. BTC/USDT:USDT, 1000PEPE/USDT:USDT). "
            "Used for list+time-series; for topic-endpoints the topic slug is derived."
        ),
    )
    p.add_argument(
        "--topic",
        default=None,
        help="Override topic slug for whatsup/news/posts (default: normalized symbol).",
    )
    p.set_defaults(handler=_handle)


async def _handle(args: argparse.Namespace) -> None:
    endpoint: Endpoint = args.endpoint
    symbol: str = args.symbol
    base = normalized_base(symbol)
    topic = (args.topic or base).lower()

    async with LunarCrushClient() as lc:
        if endpoint == "list":
            result = await lc.fetch_topic_metrics([symbol])
            data = result[base].model_dump() if base in result else {"_missing": base}
        elif endpoint == "whatsup":
            result = await lc.fetch_topic_whatsup(topic)
            data = result.model_dump() if result else {"_empty": topic}
        elif endpoint == "news":
            items = await lc.fetch_topic_news(topic)
            data = {"count": len(items), "items": [i.model_dump() for i in items[:3]]}
        elif endpoint == "posts":
            items = await lc.fetch_topic_posts(topic)
            data = {"count": len(items), "items": [i.model_dump() for i in items[:3]]}
        elif endpoint == "time_series":
            points = await lc.fetch_coin_time_series(base)
            data = {"count": len(points), "items": [p.model_dump() for p in points[:3]]}

    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
