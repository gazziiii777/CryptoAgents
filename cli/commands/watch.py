import asyncio

import typer

from app.scheduler import run_watcher_tick


def watch() -> None:
    """Run one Position Watcher tick: reconcile open positions and apply exits."""
    closed = asyncio.run(run_watcher_tick())
    typer.echo(f"watcher tick complete: {closed} position(s) closed")
