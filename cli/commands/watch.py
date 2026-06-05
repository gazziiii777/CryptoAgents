import asyncio

import typer

from app.engines.position_manager.runner import run_position_manager_once


def watch() -> None:
    """Run one position-manager cycle: reconcile open positions and apply exits."""
    closed = asyncio.run(run_position_manager_once())
    typer.echo(f"position-manager cycle complete: {closed} position(s) closed")
