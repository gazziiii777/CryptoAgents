import asyncio
import logging
import time

from app.clients.telegram.client import TelegramClient
from core.settings import settings

logger = logging.getLogger(__name__)

_last_alert: dict[str, float] = {}
_pending: set[asyncio.Task[None]] = set()


def _throttled(service: str) -> bool:
    """True, если ещё рано слать алерт по сервису (в окне cooldown).

    Мёртвый ключ бьёт на КАЖДОМ запросе (десятки в тик), поэтому без троттлинга алертов
    будет спам. Если окно прошло — фиксирует время и возвращает False (можно слать).
    """
    now = time.monotonic()
    last = _last_alert.get(service)
    if last is not None and now - last < settings.KEY_ALERT_COOLDOWN_S:
        return True
    _last_alert[service] = now
    return False


async def _send_key_dead(service: str) -> None:
    if not settings.TELEGRAM_ENABLED:
        return
    try:
        async with TelegramClient() as client:
            await client.send_message(
                f"🔑❌ <b>API KEY DEAD: {service}</b>\n"
                f"Сервис вернул 401/403 — ключ протух или неверен. Проверь "
                f"{service.upper()}_API_KEY. Данные этого сервиса сейчас не поступают."
            )
    except Exception:
        logger.error(
            "telegram: failed to send key-dead alert for %s", service, exc_info=True
        )


async def notify_key_dead(service: str) -> None:
    """Async-вход (из LLM-клиента): троттлит и шлёт Telegram-алерт о мёртвом ключе."""
    if _throttled(service):
        return
    await _send_key_dead(service)


def schedule_key_dead_alert(service: str) -> None:
    """Sync-вход (из log_api_error): троттлит и планирует алерт в текущем event loop.

    Вне event loop (нет running loop) — тихо пропускает: алерт не критичен для работы.
    """
    if _throttled(service):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_send_key_dead(service))
    _pending.add(task)
    task.add_done_callback(_pending.discard)
