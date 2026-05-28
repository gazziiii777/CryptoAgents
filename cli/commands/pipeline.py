import asyncio

import typer

from app.pipeline.runner import run_pipeline


def pipeline(
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        help="Top-N liquid pairs to run; omit for the full universe.",
    ),
) -> None:
    """Run the screener → enricher pipeline; --limit N for a smoke run, omit for full."""
    asyncio.run(run_pipeline(symbol_limit=limit))
