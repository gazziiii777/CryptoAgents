import asyncio

from app.engines.collector.runner import run_collector


def collect_liquidations() -> None:
    """Always-on сборщик: стримит ликвидации Binance USD-M в research-БД.

    Отдельный сервис от торгового worker'а — постоянный ws-стрим 24/7 с
    авто-реконнектом, не зависит от тиков пайплайна.
    """
    asyncio.run(run_collector())
