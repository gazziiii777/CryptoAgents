from app.models.analysis import TechnicalReport
from core.prompts.loader import load_prompt
from app.agents.technical.graph import analyze_technical
from app.agents.technical.levels import compute_facts
from app.agents.technical.nodes import _render_user_prompt
from app.clients.ccxt.models import OHLCVCandle
from core.settings import settings


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


class _FakeService:
    def __init__(self, report: TechnicalReport) -> None:
        self._report = report
        self.calls: list[dict[str, object]] = []

    async def structured(self, **kwargs: object) -> TechnicalReport:
        self.calls.append(kwargs)
        return self._report


def test_render_includes_symbol_and_levels():
    facts = compute_facts(_candles(40), _candles(5))
    prompt = _render_user_prompt(load_prompt("technical").user, "BTC/USDT:USDT", facts)
    assert "BTC/USDT:USDT" in prompt
    assert "Current price" in prompt
    assert "EMA20" in prompt


async def test_analyze_technical_runs_graph_and_uses_deep_model():
    report = TechnicalReport(
        market_structure="ranging near EMAs",
        htf_bias="Neutral",
        setup_bias="Neutral",
        key_levels=[],
        entry_timeframe_note="mid-range",
        signal_direction="No Signal",
        confidence=0.4,
    )
    service = _FakeService(report)

    result = await analyze_technical(
        service,  # type: ignore[arg-type]
        "BTC/USDT:USDT",
        _candles(40),
        _candles(5),
    )

    assert result.signal_direction == "No Signal"
    assert service.calls[0]["response_model"] is TechnicalReport
    assert service.calls[0]["entity_type"] == "technical"
    assert service.calls[0]["model"] == settings.LLM_DEEP_MODEL
