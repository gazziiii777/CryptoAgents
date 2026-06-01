from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.notifications.positions import (
    _format_close,
    _format_open,
    _pct,
    _r_multiple,
    _side_label,
    notify_position_closed,
    notify_position_opened,
)
from core.settings import settings
from db.models import ExitReason, PositionSide, PositionState, VirtualPosition

_ENTRY_TS = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)


def _position(**overrides: object) -> VirtualPosition:
    base = dict(
        account_id=1,
        symbol="ESPORTS/USDT:USDT",
        side=PositionSide.SHORT,
        entry_signal_id=1,
        entry_ts=_ENTRY_TS,
        entry_price=Decimal("0.0372"),
        qty=Decimal("5000"),
        notional=Decimal("186"),
        leverage=5,
        stop_price=Decimal("0.0391"),
        target_price=Decimal("0.0335"),
    )
    base.update(overrides)
    return VirtualPosition(**base)


def _closed(exit_price: Decimal, reason: ExitReason, pnl: Decimal) -> VirtualPosition:
    position = _position()
    position.state = PositionState.CLOSED
    position.exit_ts = _ENTRY_TS + timedelta(hours=4)
    position.exit_price = exit_price
    position.exit_reason = reason
    position.realized_pnl = pnl
    return position


@pytest.mark.unit
def test_format_open_contains_key_fields() -> None:
    text = _format_open(_position(), 0.52)
    assert "OPEN" in text
    assert "SHORT" in text
    assert "ESPORTS/USDT:USDT" in text
    assert "0.0372" in text
    assert "0.0391" in text
    assert "0.0335" in text
    assert "0.52" in text


@pytest.mark.unit
def test_format_close_win_shows_positive_pnl_and_r() -> None:
    text = _format_close(
        _closed(Decimal("0.0335"), ExitReason.TARGET, Decimal("29.12")),
        Decimal("2094.39"),
    )
    assert "WIN" in text
    assert "+29.12 USDT" in text
    assert "R)" in text
    assert "Balance: 2094.39 USDT" in text
    assert "(target)" in text


@pytest.mark.unit
def test_format_close_loss_shows_negative_pnl() -> None:
    text = _format_close(
        _closed(Decimal("0.0391"), ExitReason.STOP, Decimal("-12.05")),
        Decimal("2082.34"),
    )
    assert "LOSS" in text
    assert "-12.05 USDT" in text
    assert "(stop)" in text


@pytest.mark.unit
def test_side_label_distinguishes_long_short() -> None:
    assert "LONG" in _side_label(PositionSide.LONG)
    assert "SHORT" in _side_label(PositionSide.SHORT)


@pytest.mark.unit
def test_pct_handles_zero_base() -> None:
    assert _pct(Decimal("1"), Decimal("0")) == "n/a"


@pytest.mark.unit
def test_r_multiple_handles_zero_risk() -> None:
    position = _position(stop_price=Decimal("0.0372"))
    assert _r_multiple(position, Decimal("10")) == "n/a"


@pytest.mark.unit
async def test_notify_open_is_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled = settings.model_copy(
        update={"TELEGRAM_BOT_TOKEN": None, "TELEGRAM_CHAT_ID": None}
    )
    monkeypatch.setattr("app.notifications.positions.settings", disabled)
    client_cls = MagicMock()
    monkeypatch.setattr("app.notifications.positions.TelegramClient", client_cls)

    await notify_position_opened(_position(), 0.52)

    client_cls.assert_not_called()


@pytest.mark.unit
async def test_notify_close_is_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled = settings.model_copy(
        update={"TELEGRAM_BOT_TOKEN": None, "TELEGRAM_CHAT_ID": None}
    )
    monkeypatch.setattr("app.notifications.positions.settings", disabled)
    client_cls = MagicMock()
    monkeypatch.setattr("app.notifications.positions.TelegramClient", client_cls)

    await notify_position_closed(_position(), Decimal("2000"))

    client_cls.assert_not_called()
