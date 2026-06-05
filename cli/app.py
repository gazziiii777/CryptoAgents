import logging

import typer

from app.logger import setup_logging
from cli.commands import collect, keys_check, manage, monitor, pipeline, run, watch

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="TradingAgents CLI — pipeline stages and diagnostic helpers.",
)


@app.callback()
def _bootstrap(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG-level logging"),
) -> None:
    setup_logging(logging.DEBUG if verbose else logging.INFO)


app.command("keys-check")(keys_check.keys_check)
app.command("pipeline")(pipeline.pipeline)
app.command("watch")(watch.watch)
app.command("run")(run.run)
app.command("collect-liquidations")(collect.collect_liquidations)
app.command("monitor-positions")(monitor.monitor_positions)
app.command("account-create")(manage.account_create)
app.command("halt-trading")(manage.halt_trading)
app.command("resume-trading")(manage.resume_trading)
app.command("force-close")(manage.force_close)
app.command("manual-signal")(manage.manual_signal)
