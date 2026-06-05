from app.services.agents.technical.levels import compute_facts
from app.adapters.clients.ccxt.models import OHLCVCandle


def _candles(n: int, base: float = 100.0) -> list[OHLCVCandle]:
    return [
        OHLCVCandle(
            timestamp=i,
            open=base + i * 0.1,
            high=base + i * 0.1 + 1,
            low=base + i * 0.1 - 1,
            close=base + i * 0.1,
            volume=1000.0,
        )
        for i in range(n)
    ]


def test_compute_facts_basic_fields():
    facts = compute_facts(_candles(40), _candles(5))
    assert facts.current_price > 0
    assert facts.recent_high >= facts.recent_low
    assert facts.ema_20 > 0
    assert facts.ema_50 > 0
    assert facts.atr >= 0


def test_compute_facts_prev_day_from_second_to_last():
    facts = compute_facts(_candles(40), _candles(5))
    expected = _candles(5)[-2]
    assert facts.prev_day_high == expected.high
    assert facts.prev_day_low == expected.low
