import json
import logging
import os
from datetime import datetime, timezone

_RESERVED_RECORD_FIELDS = frozenset({
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
})

_LEVEL_COLORS = {
    logging.DEBUG: "\033[38;5;240m",
    logging.INFO: "\033[36m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_RESET = "\033[0m"


class JsonFormatter(logging.Formatter):
    """Один JSON-объект на строку: ts/level/logger/message + extra-поля + exc.

    При colorize=True строка тонируется ANSI-цветом по уровню — только для
    терминала; ANSI ломает машинный парсинг, поэтому в пайп/файл идёт сырой JSON.
    """

    def __init__(self, *, colorize: bool = False) -> None:
        super().__init__()
        self._colorize = colorize

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_FIELDS:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        line = json.dumps(payload, ensure_ascii=False, default=str)
        color = _LEVEL_COLORS.get(record.levelno) if self._colorize else None
        return f"{color}{line}{_RESET}" if color else line


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    colorize = handler.stream.isatty() and os.environ.get("NO_COLOR") is None
    handler.setFormatter(JsonFormatter(colorize=colorize))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
