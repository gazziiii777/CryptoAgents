import logging
from typing import Self

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import AiogramError

from app.adapters.clients.telegram.exceptions import TelegramError
from core.settings import settings

logger = logging.getLogger(__name__)

_SERVICE = "Telegram"


class TelegramClient:
    """Клиент Telegram на aiogram для исходящих уведомлений. Async context manager.

    Только отправка сообщений (это нотификатор, не бот с поллингом). Токен и chat_id
    берутся из настроек; вызывать только при settings.TELEGRAM_ENABLED. Сессия aiogram
    закрывается в __aexit__.
    """

    def __init__(self) -> None:
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            raise TelegramError("Telegram credentials are not configured")
        self._chat_id = chat_id
        self._bot = Bot(
            token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._bot.session.close()

    async def send_message(self, text: str) -> None:
        """Отправляет текстовое сообщение в настроенный чат. Бросает TelegramError при сбое."""
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
        except AiogramError as exc:
            logger.error("%s send failed: %s", _SERVICE, exc)
            raise TelegramError("failed to send Telegram message") from exc
