import pytest

from core.prompts.loader import load_prompt
from core.prompts.models import PromptTemplate


def test_load_macro_prompt_returns_template():
    prompt = load_prompt("macro")
    assert isinstance(prompt, PromptTemplate)
    assert "macro analyst" in prompt.system
    assert "$btc_price" in prompt.user


def test_load_prompt_is_cached():
    assert load_prompt("macro") is load_prompt("macro")


def test_missing_prompt_raises():
    with pytest.raises(FileNotFoundError, match="does_not_exist"):
        load_prompt("does_not_exist")
