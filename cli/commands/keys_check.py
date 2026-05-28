import typer

from app.startup import required_keys
from core.settings import settings

_NECESSITY_REQUIRED = "required"
_NECESSITY_OPTIONAL = "optional"

_KEY_WIDTH = 22
_STATUS_WIDTH = 10
_NECESSITY_WIDTH = 10
_SEPARATOR_WIDTH = 60
_MASK_VISIBLE_CHARS = 4
_MASK_MIN_LENGTH = 8


def _mask(value: str) -> str:
    if not value:
        return "—"
    if len(value) <= _MASK_MIN_LENGTH:
        return "***"
    return f"{value[:_MASK_VISIBLE_CHARS]}…{value[-_MASK_VISIBLE_CHARS:]}"


def keys_check() -> None:
    """Show which API keys are configured (without printing their values)."""
    required = required_keys()
    all_keys = {
        "LUNARCRUSH_API_KEY": settings.LUNARCRUSH_API_KEY,
        "COINGLASS_API_KEY": settings.COINGLASS_API_KEY,
        "COINGECKO_API_KEY": settings.COINGECKO_API_KEY,
        "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
        "OPENAI_API_KEY": settings.OPENAI_API_KEY,
    }
    rows = [
        (name, value, _NECESSITY_REQUIRED if name in required else _NECESSITY_OPTIONAL)
        for name, value in all_keys.items()
    ]
    typer.echo(
        f"{'KEY':<{_KEY_WIDTH}} {'STATUS':<{_STATUS_WIDTH}} "
        f"{'NECESSITY':<{_NECESSITY_WIDTH}} VALUE"
    )
    typer.echo("-" * _SEPARATOR_WIDTH)
    missing_required = 0
    for name, value, necessity in rows:
        status = "set" if value else "MISSING"
        if not value and necessity == _NECESSITY_REQUIRED:
            missing_required += 1
        typer.echo(
            f"{name:<{_KEY_WIDTH}} {status:<{_STATUS_WIDTH}} "
            f"{necessity:<{_NECESSITY_WIDTH}} {_mask(value)}"
        )
    if missing_required:
        raise typer.Exit(code=1)
