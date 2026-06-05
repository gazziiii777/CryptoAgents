import asyncio

from app.monitor.runner import run_monitor


def monitor_positions() -> None:
    """Always-on монитор открытых позиций: алерты о сдвиге стопа (безубыток/трейлинг) раз в 5 мин.

    Отдельный сервис от worker'а: лёгкий цикл по ценам, не закрывает позиции
    (close остаётся за 4h-watcher), только near-real-time видимость.
    """
    asyncio.run(run_monitor())
