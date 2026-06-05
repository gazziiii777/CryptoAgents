class CoinGlassAuthError(RuntimeError):
    """API key is missing, invalid, or has insufficient permissions."""


class CoinGlassAPIError(RuntimeError):
    """CoinGlass вернул HTTP 200 с code != 0 (напр. 'Server Error' — нет данных по символу).

    Доброкачественный per-symbol случай: эндпоинт жив, но по конкретной монете данных нет.
    Системные сбои (исчерпание rate-limit, сеть, смена контракта) бросаются отдельно
    (RuntimeError / httpx-ошибки) и должны оставаться громкими в логах.
    """
