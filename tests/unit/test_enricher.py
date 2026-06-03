from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.clients.coingecko.models import MacroSnapshot
from app.enricher.enricher import _NEUTRAL_MACRO, DataEnricher


@pytest.mark.unit
async def test_fetch_macro_degrades_to_neutral_on_http_error():
    coingecko = MagicMock()
    coingecko.fetch_macro_snapshot = AsyncMock(side_effect=httpx.ConnectError("boom"))

    result = await DataEnricher()._fetch_macro(coingecko)

    assert result is _NEUTRAL_MACRO


@pytest.mark.unit
async def test_fetch_macro_passthrough_on_success():
    snapshot = MacroSnapshot(
        btc_dominance=55.0,
        btc_price_usd=60000.0,
        btc_change_24h=1.0,
        btc_change_7d=2.0,
        total_market_cap_change_24h=0.5,
    )
    coingecko = MagicMock()
    coingecko.fetch_macro_snapshot = AsyncMock(return_value=snapshot)

    result = await DataEnricher()._fetch_macro(coingecko)

    assert result is snapshot


@pytest.mark.unit
async def test_fetch_lc_metrics_degrades_to_empty_on_http_error():
    lunarcrush = MagicMock()
    lunarcrush.fetch_topic_metrics = AsyncMock(side_effect=httpx.ConnectError("boom"))

    result = await DataEnricher()._fetch_lc_metrics(lunarcrush, ["BTC/USDT:USDT"])

    assert result == {}
