class LLMBudgetExceededError(RuntimeError):
    """Дневной бюджет LLM исчерпан — новые вызовы блокируются до следующих UTC-суток."""
