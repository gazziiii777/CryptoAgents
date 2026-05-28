_LEVERAGE_PREFIXES = ("1000000", "10000", "1000", "1M")


def base_currency(symbol: str) -> str:
    """'BTC/USDT:USDT' → 'BTC'. Базовая монета из ccxt swap-формата."""
    return symbol.split("/")[0]


def normalized_base(symbol: str) -> str:
    """Базовая монета без биржевого leverage-префикса.

    Binance perp использует префиксы '1000', '1M' и т.п. для дешёвых мемкоинов
    ('1000PEPE' = 1000 × PEPE, '1MBABYDOGE' = 1_000_000 × BABYDOGE). Для запросов
    к социальным/новостным сервисам префикс нужно убирать, иначе охват = 0.
    """
    base = base_currency(symbol)
    for prefix in _LEVERAGE_PREFIXES:
        if base.startswith(prefix):
            stripped = base[len(prefix) :]
            if stripped.isalpha() and len(stripped) >= 2:
                return stripped
    return base


def to_exchange_pair(symbol: str) -> str:
    """'BTC/USDT:USDT' → 'BTCUSDT'. Торговая пара без разделителей.

    Используется для Binance FAPI и CoinGlass per-exchange эндпоинтов.
    """
    parts = symbol.split("/")
    if len(parts) != 2 or ":" not in parts[1]:
        raise ValueError(f"Unexpected ccxt symbol format: {symbol!r}")
    return parts[0] + parts[1].split(":")[0]


def to_ccxt_perp_symbol(base: str, quote: str) -> str:
    """'BTC', 'USDT' → 'BTC/USDT:USDT'. Собирает ccxt swap-символ из базы и quote."""
    return f"{base}/{quote}:{quote}"
