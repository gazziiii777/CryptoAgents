_DEFAULT_LEVERAGE = 3

_LEVERAGE_TABLE: dict[tuple[str, str], int] = {
    ("trend_continuation", "conservative"): 3,
    ("trend_continuation", "moderate"): 5,
    ("trend_continuation", "aggressive"): 8,
    ("breakout", "conservative"): 3,
    ("breakout", "moderate"): 5,
    ("breakout", "aggressive"): 7,
    ("reversal", "conservative"): 2,
    ("reversal", "moderate"): 3,
    ("reversal", "aggressive"): 5,
}


def compute_leverage(setup_type: str, leverage_intent: str, max_leverage: int) -> int:
    """Детерминированное плечо из (setup_type, символьный intent LLM), capped max_leverage.

    LLM выбирает только категорию агрессии (conservative/moderate/aggressive),
    число задаёт таблица — это держит управление деньгами вне LLM. Неизвестная
    пара → консервативный дефолт. Cap (settings.MAX_LEVERAGE) передаётся вызывающим.
    """
    base = _LEVERAGE_TABLE.get((setup_type, leverage_intent), _DEFAULT_LEVERAGE)
    return max(1, min(max_leverage, base))
