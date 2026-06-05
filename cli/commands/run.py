import asyncio

import typer

from app.exceptions import StartupError
from app.engines.worker.scheduler import run_forever, run_once
from app.startup import preflight


def run(
    once: bool = typer.Option(False, "--once", help="Run a single tick and exit"),
    limit: int | None = typer.Option(
        None, "--limit", "-n", min=1, help="Top-N pairs (smoke); omit for full universe"
    ),
) -> None:
    """Scheduler loop: every 4h bar close runs the pipeline (screen → agents → open).

    Проверяет ключи перед стартом (fail-fast). Миграции применяются ОТДЕЛЬНО —
    локально через `make up`, на проде через `make deploy.migrate` или вручную
    `docker compose run --rm app alembic upgrade head`. Worker не мигрирует сам.
    """
    try:
        preflight()
    except StartupError as exc:
        typer.echo(f"startup failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if once:
        asyncio.run(run_once(limit))
    else:
        asyncio.run(run_forever(limit))
