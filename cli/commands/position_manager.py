import asyncio

from app.engines.position_manager.runner import run_position_manager


def manage_positions() -> None:
    """Always-on движок управления позициями: исполняет выходы + алерты о сдвиге стопа.

    Отдельный сервис от worker'а и единственный писатель выходов: каждые
    POSITION_MANAGER_INTERVAL_S реконструирует управляемый стоп по 15m-свечам и закрывает
    позиции (стоп/тейк/безубыток/трейлинг/экспирация/funding/делистинг), обновляет equity.
    """
    asyncio.run(run_position_manager())
