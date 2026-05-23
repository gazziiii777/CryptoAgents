from __future__ import annotations

import logging

_COLORS = {
    logging.DEBUG: "\033[38;5;240m",
    logging.INFO: "\033[36m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelno, "")
        msg = super().format(record)
        return f"{color}{msg}{_RESET}" if color else msg


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        ColorFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s — %(message)s", datefmt="%H:%M:%S"
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
