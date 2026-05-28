from app.models.analysis import SignalSynthesis
from app.models.setup import CryptoSetup, FinalSignal


def format_signal(
    symbol: str, synthesis: SignalSynthesis, setup: CryptoSetup
) -> FinalSignal:
    """Собирает FinalSignal из цен (CryptoSetup) и синтеза (bias/confluence/риски)."""
    return FinalSignal(
        symbol=symbol,
        direction=setup.direction,
        setup_type=setup.setup_type,
        entry_price=setup.entry_price,
        stop_price=setup.stop_price,
        target_price=setup.target_price,
        risk_reward=setup.risk_reward,
        valid_hours=setup.valid_hours,
        confluence_score=synthesis.confluence_score,
        invalidation=setup.invalidation,
        thesis=synthesis.reasoning,
        key_risks=synthesis.top_risks,
        leverage_intent=setup.leverage_intent,
    )
