from app.services.screener.universe import _filter_perp_pairs, _intersect_universe


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


def test_keeps_market_without_underlying_type_when_gate_off():
    markets = {
        "WAT/USDT:USDT": {"swap": True, "base": "WAT", "quote": "USDT", "active": True}
    }
    tickers = {"WAT/USDT:USDT": {"quoteVolume": 1e9}}

    result = _filter_perp_pairs(
        markets, tickers, "USDT", 5e6, require_coin_underlying=False
    )
    assert result == ["WAT/USDT:USDT"]


def test_intersect_keeps_only_tradable_preserving_order():
    primary = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "FOO/USDT:USDT"]
    tradable = {"SOL/USDT:USDT", "BTC/USDT:USDT"}

    assert _intersect_universe(primary, tradable) == ["BTC/USDT:USDT", "SOL/USDT:USDT"]


def test_intersect_no_overlap_yields_empty():
    assert _intersect_universe(["AAA/USDT:USDT"], {"BBB/USDT:USDT"}) == []
