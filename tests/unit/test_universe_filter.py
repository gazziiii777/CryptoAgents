from app.screener.universe import _filter_perp_pairs


def _market(underlying_type: str, base: str = "BTC") -> dict[str, object]:
    return {
        "swap": True,
        "base": base,
        "quote": "USDT",
        "active": True,
        "info": {"underlyingType": underlying_type},
    }


def test_excludes_commodity_perps():
    markets = {
        "BTC/USDT:USDT": _market("COIN", "BTC"),
        "XAU/USDT:USDT": _market("COMMODITY", "XAU"),
        "CL/USDT:USDT": _market("COMMODITY", "CL"),
    }
    tickers = {sym: {"quoteVolume": 1e9} for sym in markets}

    result = _filter_perp_pairs(markets, tickers, "USDT", 5e6)

    assert "BTC/USDT:USDT" in result
    assert "XAU/USDT:USDT" not in result
    assert "CL/USDT:USDT" not in result


def test_keeps_coin_perps():
    markets = {"BSB/USDT:USDT": _market("COIN", "BSB")}
    tickers = {"BSB/USDT:USDT": {"quoteVolume": 1e7}}

    assert _filter_perp_pairs(markets, tickers, "USDT", 5e6) == ["BSB/USDT:USDT"]


def test_excludes_gold_stable_wrapped_bases():
    markets = {
        "ETH/USDT:USDT": _market("COIN", "ETH"),
        "XAUT/USDT:USDT": _market("COIN", "XAUT"),
        "USDC/USDT:USDT": _market("COIN", "USDC"),
        "WBTC/USDT:USDT": _market("COIN", "WBTC"),
    }
    tickers = {sym: {"quoteVolume": 1e9} for sym in markets}

    result = _filter_perp_pairs(markets, tickers, "USDT", 5e6)

    assert result == ["ETH/USDT:USDT"]


def test_excludes_non_ascii_base():
    markets = {
        "ETH/USDT:USDT": _market("COIN", "ETH"),
        "币安人生/USDT:USDT": _market("COIN", "币安人生"),
    }
    tickers = {sym: {"quoteVolume": 1e9} for sym in markets}

    result = _filter_perp_pairs(markets, tickers, "USDT", 5e6)

    assert "币安人生/USDT:USDT" not in result
    assert "ETH/USDT:USDT" in result


def test_excludes_market_without_underlying_type():
    markets = {"WAT/USDT:USDT": {"swap": True, "quote": "USDT", "active": True}}
    tickers = {"WAT/USDT:USDT": {"quoteVolume": 1e9}}

    assert _filter_perp_pairs(markets, tickers, "USDT", 5e6) == []
