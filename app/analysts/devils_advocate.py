import logging
from string import Template

from app.llm_gateway.service import LLMService
from app.models.analysis import DevilsAdvocateReport, SignalSynthesis
from app.models.setup import CryptoSetup
from core.prompts.loader import load_prompt
from core.settings import settings

logger = logging.getLogger(__name__)

_ENTITY_TYPE = "devils_advocate"
_CRITICAL_THRESHOLD = 2
_PENALTY = 0.15
_BOOST = 0.05


async def run_devils_advocate(
    service: LLMService,
    symbol: str,
    synthesis: SignalSynthesis,
    setup: CryptoSetup,
    manipulation_context: str,
) -> DevilsAdvocateReport:
    """Red-team готового сетапа (deep-модель): ищет trade-invalidating риски."""
    prompt = load_prompt(_ENTITY_TYPE)
    user = Template(prompt.user).substitute(
        symbol=symbol,
        direction=setup.direction,
        setup_type=setup.setup_type,
        entry=f"{setup.entry_price:.6g}",
        stop=f"{setup.stop_price:.6g}",
        target=f"{setup.target_price:.6g}",
        risk_reward=f"{setup.risk_reward:.2f}",
        bias=synthesis.overall_bias,
        confluence=f"{synthesis.confluence_score:.2f}",
        thesis=synthesis.reasoning,
        manipulation_context=manipulation_context,
    )
    return await service.structured(
        model=settings.LLM_DEEP_MODEL,
        system=prompt.system,
        user=user,
        response_model=DevilsAdvocateReport,
        entity_type=_ENTITY_TYPE,
    )


def apply_devils_advocate(
    synthesis: SignalSynthesis, report: DevilsAdvocateReport
) -> SignalSynthesis:
    """Корректирует confluence по числу critical_risks.

    >= 2 критичных риска → −0.15 (вероятный veto через гейт); 0 → +0.05 (чистый сетап);
    1 → без изменений. Critical-риски добавляются в top_risks для прозрачности.
    """
    risk_count = len(report.critical_risks)
    if risk_count >= _CRITICAL_THRESHOLD:
        delta = -_PENALTY
    elif risk_count == 0:
        delta = _BOOST
    else:
        delta = 0.0
    new_confluence = max(0.0, min(1.0, synthesis.confluence_score + delta))
    return synthesis.model_copy(
        update={
            "confluence_score": new_confluence,
            "top_risks": synthesis.top_risks + report.critical_risks,
        }
    )
