class LLMCompletionError(RuntimeError):
    """Вызов LLM не вернул валидный structured-результат (сетевой сбой, schema, провайдер)."""
