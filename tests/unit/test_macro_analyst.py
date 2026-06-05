from app.services.analysts.macro import _render_user_prompt, analyze_macro
from app.domain.models.analysis import MacroReport
from core.prompts.loader import load_prompt
from app.adapters.clients.coingecko.models import MacroSnapshot

_MACRO = MacroSnapshot(
    btc_dominance=58.1,
    btc_price_usd=76669.0,
    btc_change_24h=1.07,
    btc_change_7d=-1.95,
    total_market_cap_change_24h=0.88,
)


class _FakeService:
    def __init__(self, report: MacroReport) -> None:
        self._report = report
        self.calls: list[dict[str, object]] = []

    async def structured(self, **kwargs: object) -> MacroReport:
        self.calls.append(kwargs)
        return self._report


def test_render_user_prompt_includes_snapshot_fields():
    template = load_prompt("macro").user
    prompt = _render_user_prompt(template, _MACRO, fear_greed=64)
    assert "$76,669" in prompt
    assert "58.10%" in prompt
    assert "64" in prompt


def test_render_user_prompt_handles_missing_fear_greed():
    template = load_prompt("macro").user
    assert "n/a" in _render_user_prompt(template, _MACRO, fear_greed=None)


async def test_analyze_macro_passes_response_model_and_returns_report():
    expected = MacroReport(
        regime="Trending Up",
        btc_bias="Bullish",
        dominance_trend="Rising",
        alts_tradeable=True,
        reasoning="strong momentum",
    )
    service = _FakeService(expected)

    result = await analyze_macro(service, _MACRO, fear_greed=64)  # type: ignore[arg-type]

    assert result is expected
    assert service.calls[0]["response_model"] is MacroReport
    assert service.calls[0]["entity_type"] == "macro"
