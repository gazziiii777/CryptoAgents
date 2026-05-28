from functools import cache
from pathlib import Path

import yaml

from core.prompts.models import PromptTemplate

_PROMPTS_DIR = Path(__file__).parent


@cache
def load_prompt(name: str) -> PromptTemplate:
    """Загрузить промпт из core/prompts/<name>.yaml (кэшируется)."""
    raw = yaml.safe_load((_PROMPTS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    return PromptTemplate.model_validate(raw)
