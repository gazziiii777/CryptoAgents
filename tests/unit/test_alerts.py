from unittest.mock import MagicMock

import pytest

from app.notifications import alerts


@pytest.mark.unit
def test_throttle_blocks_repeat_within_cooldown() -> None:
    alerts._last_alert.clear()
    assert alerts._throttled("SVC") is False  # первый раз — можно
    assert alerts._throttled("SVC") is True  # сразу повтор — троттл


@pytest.mark.unit
def test_throttle_is_per_service() -> None:
    alerts._last_alert.clear()
    assert alerts._throttled("A") is False
    assert alerts._throttled("B") is False  # другой сервис — независимо


@pytest.mark.unit
async def test_notify_key_dead_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts._last_alert.clear()
    client_cls = MagicMock()
    monkeypatch.setattr("app.notifications.alerts.TelegramClient", client_cls)

    await alerts.notify_key_dead("SVC")

    client_cls.assert_not_called()


@pytest.mark.unit
async def test_schedule_key_dead_alert_no_loop_is_safe() -> None:
    # вызов вне event loop не должен падать (нет running loop при синхронном вызове)
    alerts._last_alert.clear()
    alerts.schedule_key_dead_alert("SVC")
