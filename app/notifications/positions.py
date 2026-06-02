import logging
from dataclasses import dataclass
from decimal import Decimal

from app.clients.telegram.client import TelegramClient
from core.constants.time import SECONDS_PER_HOUR
from core.settings import settings
from db.models import PositionSide, VirtualPosition

logger = logging.getLogger(__name__)

_PRICE_PRECISION = 6
_HUNDRED = Decimal(100)


@dataclass
class _Labels:
    OPEN_HEADER: str = "🟢 <b>OPEN</b>"
    WIN_HEADER: str = "🟢 <b>CLOSED · WIN</b>"
    LOSS_HEADER: str = "🔴 <b>CLOSED · LOSS</b>"
    SIDE_LONG: str = "🟩 LONG"
    SIDE_SHORT: str = "🟥 SHORT"


def _side_label(side: PositionSide) -> str:
    return _Labels.SIDE_LONG if side == PositionSide.LONG else _Labels.SIDE_SHORT


def _price(value: Decimal) -> str:
    return f"{value:.{_PRICE_PRECISION}g}"


def _pct(value: Decimal, base: Decimal) -> str:
    if base == 0:
        return "n/a"
    return f"{(value - base) / base * _HUNDRED:+.2f}%"


def _r_multiple(position: VirtualPosition, realized_pnl: Decimal) -> str:
    risk = abs(position.entry_price - position.stop_price) * position.qty
    if risk == 0:
        return "n/a"
    return f"{realized_pnl / risk:+.2f}R"


def _return_on_margin(position: VirtualPosition, realized_pnl: Decimal) -> str:
    margin = position.margin or Decimal(0)
    if margin == 0:
        return ""
    return f", {realized_pnl / margin * _HUNDRED:+.1f}% маржи"


def _format_open(position: VirtualPosition, confluence_score: float) -> str:
    leverage = f"×{position.leverage}" if position.leverage else "×1"
    notional = position.notional or Decimal(0)
    margin = position.margin or Decimal(0)
    return (
        f"{_Labels.OPEN_HEADER}  {_side_label(position.side)} {leverage}\n"
        f"<b>{position.symbol}</b>\n"
        f"Entry:  <code>{_price(position.entry_price)}</code>\n"
        f"Stop:   <code>{_price(position.stop_price)}</code> "
        f"({_pct(position.stop_price, position.entry_price)})\n"
        f"Target: <code>{_price(position.target_price)}</code> "
        f"({_pct(position.target_price, position.entry_price)})\n"
        f"💵 Размер: <b>{notional:.2f} USDT</b>  плечо {leverage}  (маржа {margin:.2f} USDT)\n"
        f"Confluence: {confluence_score:.2f}"
    )


def _holding_hours(position: VirtualPosition) -> float:
    if position.exit_ts is None:
        return 0.0
    return (position.exit_ts - position.entry_ts).total_seconds() / SECONDS_PER_HOUR


def _format_close(position: VirtualPosition, balance: Decimal) -> str:
    realized_pnl = position.realized_pnl or Decimal(0)
    header = _Labels.WIN_HEADER if realized_pnl >= 0 else _Labels.LOSS_HEADER
    exit_price = position.exit_price or Decimal(0)
    reason = position.exit_reason.value if position.exit_reason else "n/a"
    return (
        f"{header}  {_side_label(position.side)}\n"
        f"<b>{position.symbol}</b>  ({reason})\n"
        f"Entry → Exit: <code>{_price(position.entry_price)}</code> → "
        f"<code>{_price(exit_price)}</code> "
        f"({_pct(exit_price, position.entry_price)})\n"
        f"PnL: <b>{realized_pnl:+.2f} USDT</b>  "
        f"({_r_multiple(position, realized_pnl)}"
        f"{_return_on_margin(position, realized_pnl)})\n"
        f"Hold: {_holding_hours(position):.1f}h\n"
        f"Balance: {balance:.2f} USDT"
    )


async def notify_position_opened(
    position: VirtualPosition, confluence_score: float
) -> None:
    """Шлёт уведомление об открытии позиции в Telegram. Сбой не ломает торговлю."""
    if not settings.TELEGRAM_ENABLED:
        return
    try:
        async with TelegramClient() as client:
            await client.send_message(_format_open(position, confluence_score))
    except Exception:
        logger.error("telegram: failed to notify open", exc_info=True)


async def notify_position_closed(position: VirtualPosition, balance: Decimal) -> None:
    """Шлёт уведомление о закрытии позиции (плюс/минус) в Telegram. Сбой не ломает торговлю."""
    if not settings.TELEGRAM_ENABLED:
        return
    try:
        async with TelegramClient() as client:
            await client.send_message(_format_close(position, balance))
    except Exception:
        logger.error("telegram: failed to notify close", exc_info=True)
