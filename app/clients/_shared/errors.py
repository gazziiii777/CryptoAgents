from __future__ import annotations

import logging

import httpx

_AUTH_STATUSES = (401, 403)
_RATE_LIMIT_STATUS = 429


def log_api_error(service: str, exc: BaseException, *, path: str | None = None) -> None:
    """Единое логирование HTTP-ошибки клиента с явной диагностикой ключа.

    Различает три кейса, чтобы их сразу было видно в логе:
      - 401/403 → ERROR "<service> API KEY INVALID OR EXPIRED" (ключ протух/неверный/без прав)
      - 429    → WARNING "<service> RATE LIMIT EXCEEDED" (квота)
      - прочее → WARNING с типом исключения и статусом, если есть

    Использовать в except-блоках клиентов вместо ad-hoc warn'ов с разным форматом.
    """
    logger = logging.getLogger(f"app.clients.{service.lower()}")
    where = f" [{path}]" if path else ""

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in _AUTH_STATUSES:
            logger.error(
                "%s API KEY INVALID OR EXPIRED (status %d)%s — check %s_API_KEY env var",
                service,
                status,
                where,
                service.upper(),
            )
            return
        if status == _RATE_LIMIT_STATUS:
            logger.warning(
                "%s RATE LIMIT EXCEEDED (status 429)%s — request was throttled",
                service,
                where,
            )
            return
        logger.warning("%s HTTP %d%s: %s", service, status, where, exc)
        return

    if isinstance(exc, httpx.TimeoutException):
        logger.warning("%s TIMEOUT%s after request", service, where)
        return

    if isinstance(exc, httpx.NetworkError):
        logger.warning("%s NETWORK ERROR%s: %s", service, where, exc)
        return

    if isinstance(exc, httpx.HTTPError):
        logger.warning("%s HTTP error%s: %s", service, where, exc)
        return

    logger.warning(
        "%s unexpected error%s (%s): %s", service, where, type(exc).__name__, exc
    )


def log_key_status(service: str, key_value: str, *, optional: bool = False) -> None:
    """Стартовое логирование статуса ключа клиента.

    Без ключа: WARNING для обязательных (degraded режим виден сразу при инициализации),
    INFO для опциональных. С ключом: DEBUG — чтобы не шуметь, но при verbose-логе видно.
    """
    logger = logging.getLogger(f"app.clients.{service.lower()}")
    if not key_value:
        if optional:
            logger.info(
                "%s: API key not set (optional) — running without authentication",
                service,
            )
        else:
            logger.warning(
                "%s: API key NOT SET — client will return empty results (degraded mode)",
                service,
            )
        return
    masked = f"{key_value[:4]}…{key_value[-4:]}" if len(key_value) > 8 else "***"
    logger.debug("%s: API key configured (%s)", service, masked)
