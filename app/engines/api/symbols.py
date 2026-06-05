from core.constants.markets import QUOTE_CURRENCY

API_BASES: tuple[str, ...] = (
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "DOGE",
    "ADA",
    "AVAX",
    "LINK",
    "SUI",
)


def ccxt_symbol(base: str) -> str:
    return f"{base}/{QUOTE_CURRENCY}:{QUOTE_CURRENCY}"


def display_symbol(base: str) -> str:
    return f"{base}/{QUOTE_CURRENCY}"


def base_from_ccxt(symbol: str) -> str:
    return symbol.split("/", 1)[0]
