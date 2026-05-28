from app.screener.universe import _filter_perp_pairs


def _market(underlying_type: str) -> dict[str, object]:
    return {
        "swap": True,
        "quote": "USDT",
        "active": True,
        "info": {"underlyingType": underlying_type},
    }


def test_excludes_commodity_perps():
    markets = {
        "BTC/USDT:USDT": _market("COIN"),
        "XAU/USDT:USDT": _market("COMMODITY"),
        "CL/USDT:USDT": _market("COMMODITY"),
    }
    tickers = {sym: {"quoteVolume": 1e9} for sym in markets}

    result = _filter_perp_pairs(markets, tickers, "USDT", 5e6)

    assert "BTC/USDT:USDT" in result
    assert "XAU/USDT:USDT" not in result
    assert "CL/USDT:USDT" not in result


def test_keeps_coin_perps():
    markets = {"BSB/USDT:USDT": _market("COIN")}
    tickers = {"BSB/USDT:USDT": {"quoteVolume": 1e7}}

    assert _filter_perp_pairs(markets, tickers, "USDT", 5e6) == ["BSB/USDT:USDT"]


def test_excludes_market_without_underlying_type():
    markets = {"WAT/USDT:USDT": {"swap": True, "quote": "USDT", "active": True}}
    tickers = {"WAT/USDT:USDT": {"quoteVolume": 1e9}}

    assert _filter_perp_pairs(markets, tickers, "USDT", 5e6) == []
